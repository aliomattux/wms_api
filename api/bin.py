from odoo import api, fields, models, SUPERUSER_ID, _
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def bin_search(self, search_term=False, limit=5):
        bin_obj = self.env['bin']
        results = []
        if search_term:
            bins = bin_obj.search([('name', 'ilike', search_term)], limit=limit)
            if bins:
                bin_ids = bins.mapped('id')
                query = "SELECT id, internalid, name FROM bin"
                if len(bin_ids) > 1:
                    query += "\nWHERE id IN %s"%str(tuple(bin_ids))
                else:
                    query += "\nWHERE id = %s" % bin_ids[0]

                self.env.cr.execute(query)
                results = self.env.cr.dictfetchall()

        return {'search_results': results}


    def get_bin_exists(self, request_data):
        if not request_data.get('name_text'):
            return {'result': 'success', 'record': {}}

        bin_obj = self.env['bin']
        bin_data = {}
        bin_id = self.get_bin_exists_sql(request_data['name_text'])
        if bin_id:
            bin = bin_obj.browse(int(bin_id))
            bin_data = {'name': bin.name, 'id': bin.id}

        return {'result': 'success', 'record': bin_data}


    def return_response(self, success, error_message, record={}):
        vals = {
            'success': success,
            'record': record,
        }

        if error_message:
            vals['error_message'] = error_message

        return vals


    def upsert_license_plate(self, data):
        if not data:
            return self.return_response(True, False)

        lp_text = data['lp_text']
        receive_bin_text = data.get('receive_bin_text')
        search_type = data['search_type']
        reception_id = data['reception_id']

        if search_type == 'lp':
            bin_id = self.get_bin_exists_sql(lp_text)
            if bin_id:
                return self.return_response(False, 'You scanned a bin not an LP! LP scan should come before Bin')

        lp_obj = self.env['license.plate']
        bin_obj = self.env['bin']
        bin = False
        if receive_bin_text:
            bin_id = self.get_bin_exists_sql(receive_bin_text)
            if bin_id:
                bin = bin_obj.browse(int(bin_id))
            elif search_type in ['bin', 'all']:
                return self.return_response(False, 'Bin was not found')
        elif search_type == 'all':
             return self.return_response(False, 'Bin was not provided')

        lp_data = {}
        lps = lp_obj.search([('name', '=', lp_text)])
        if lps:
            lp = lps[0]
            if lp.status != 'Open':
                return self.return_response(False, 'This LP is already completed and cannot be used')

            if lp.reception and str(lp.reception.id) != str(reception_id):
                return self.return_response(False, 'This LP is used in a different reception.')

            if bin:
                lp.bin =  bin.id

        else:
            vals = {
                'status': 'Open',
                'name': lp_text,
                'reception': reception_id,
            }

            if bin:
                vals['bin'] = bin.id

            lp = lp_obj.create(vals)

        lp_data = {'lp_text': lp.name, 'id': lp.id, 'bin_text': lp.bin.name}
        return self.return_response(True, False, lp_data)


    def get_bin_inventory(self, bin_data):
        """
          {'data': {'112083': {'internalid': '112083',
                              'inventory': [{'ddn': '71548-A',
                                             'internalid': '23279',
                                             'item': 'SR010616TG48-trex_deck_trns-sr-54x6-16ft-grv',
                                             'mpn': 'SR010616TG48',
                                             'preferred': True,
                                             'qty_available': '1091',
                                             'qty_onhand': '1091',
                                             'sku': 'SR010616TG48',
                                             'status': '1',
                                             'upc': '652835062458'},
                                            {'ddn': '89517-A',
                                             'internalid': '43114',
                                             'item': 'TS010616E2G56-trex_deck_enhnat-TS-1x55-16ft-grv',
                                             'mpn': 'TS010616E2G56',
                                             'preferred': True,
                                             'qty_available': '324',
                                             'qty_onhand': '324',
                                             'sku': 'TS010616E2G56',
                                             'status': '1',
                                             'upc': '652835289329'}],
                              'location_internalid': '2',
                              'location_name': 'Indianapolis FC',
                              'name': '2C-36-01A',
                              'type': '',
                              'type_internalid': ''}},
          'error_message': None,
          'success': True}
        """
        bin_internalids = bin_data['bin_internalids']
        include_product_data = bin_data['include_product_data']

        bin_obj = self.env['bin']
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)

        conn = netsuite_obj.connection(netsuite, url_override=netsuite.mobile_url)
        vals = {
            'operation': 'get_bin_inventory',
            'bin_ids': bin_internalids,
        }

        res = conn.request(vals)
        if not include_product_data:
            return res

        product_internalids = []
        #This is a terrible solution but only the integrator has the product image links
        if res.get('data'):
            for bin_id, bin_data in res['data'].items():
                for product in bin_data['inventory']:
                    product_internalid = product['internalid']
                    if product_internalid not in product_internalids:
                        product_internalids.append(product_internalid)

        product_obj = self.env['product']
        mapping_dict = {}
        products = product_obj.search([('internalid', 'in', product_internalids)])
        for product in products:
            mapping_dict[product.internalid] = product.img_path

        for bin_id, bin_data in res['data'].items():
            for product in bin_data['inventory']:
                if mapping_dict.get(product['internalid']):
                    product['img_path'] = mapping_dict[product['internalid']]
        return res


    def get_bin(self, location_id):
        location_obj = self.env['bin']
        location = location_obj.browse(int(location_id))
        res = {'location_id': location.internalid, 'name': location.name}
        items = []
        res['items'] = items

        return res


    def get_bin_exists_sql(self, bin_string):
        self.env.cr.execute("SELECT id FROM bin WHERE LOWER(name) = LOWER('%s')"%bin_string)
        res = self.env.cr.fetchone()
        if not res:
            return False

        return res[0]


    def get_lp_exists_sql(self, lp_string):
        self.env.cr.execute("SELECT id FROM license_plate WHERE LOWER(name) = LOWER('%s')"%bin_string)
        res = self.env.cr.fetchone()
        if not res:
            return False

        return res[0]
