
from odoo import api, fields, models, SUPERUSER_ID, _
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def get_license_plate_putaway_details(self, license_plate_id):
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)

        lp_obj = self.env['license.plate']
        license_plate = lp_obj.browse(int(license_plate_id))
        product_internalids = []
        for lp_line in license_plate.products:
            if lp_line.product_internalid:
                product_internalids.append(lp_line.product_internalid)

        conn = netsuite_obj.connection(netsuite, url_override=netsuite.mobile_url)
        vals = {
            'operation': 'get_multi_inventory',
            'product_ids': product_internalids,
        }

        netsuite_data = conn.request(vals)
        #{'result': {'17852': {
        #     'bin_inventory': [{
        #         'bin': '2D-34-01',
        #         'bin_type': '',
        #         'bin_type_internalid': '',
        #         'internalid': '30354',
        #         'location_internalid': '2',
        #         'location_name': 'Indianapolis FC',
        #         'qty_available': '101',
        #         'qty_onhand': '101',
        #         'status': '1'
        #     }],
        # 'item_id': '17852'}}}
        lp_inventory = netsuite_data['data']
        lp_bin_internalid = license_plate.bin.internalid

        lp_vals = {
            'lp_id': license_plate.id,
            'name': license_plate.name,
            'date': license_plate.date,
            'receiving_bin': {
                'internalid': license_plate.bin.internalid,
                'id': license_plate.bin.id,
                'name': license_plate.bin.name
            },
            'status': license_plate.status,
            'reception_id': license_plate.reception.id,
            'reception_name': license_plate.reception.name,
            'show_force_complete': False if license_plate.status == 'Putaway' else True,
            'lines': {}
        }

        for lp_line in license_plate.products:
            product_internalid = lp_line.product_internalid
            item_inventory = lp_inventory.get(product_internalid)
            preferred_bin_name = None
            preferred_bin_id = None
            preferred_bin_onhand = None
            receive_bin_onhand = 0
            receive_bin_available = 0


            if not item_inventory:
                bin_inventory = []
            else:
                bin_inventory = item_inventory['bin_inventory']
                for bin in bin_inventory:
                    if str(bin['internalid']) == str(lp_bin_internalid) and not bin['preferred']:
                        receive_bin_onhand = float(bin['qty_onhand'])
                        receive_bin_available = float(bin['qty_available'])
                    if bin['preferred']:
                        preferred_bin_name = bin['bin']
                        preferred_bin_id = bin['internalid']
                        preferred_bin_onhand = bin['qty_onhand']

            qty_remaining = lp_line.qty - lp_line.qty_putaway

            if lp_vals['lines'].get(product_internalid):
                lp_vals['lines'][product_internalid]['qty_remaining'] += qty_remaining
                lp_vals['lines'][product_internalid]['qty_received'] += lp_line.qty
                lp_vals['lines'][product_internalid]['qty_putaway'] += lp_line.qty_putaway
                lp_vals['lines'][product_internalid]['line_ids'].append(lp_line.id)

            else:
                img_path = lp_line.product.img_path
                img_no_selection = 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg'
                if img_path == 'https://www.decksdirect.com/media/catalog/productno_selection' or not img_path:
                    img_path = img_no_selection

                item_res = {
                    'product_internalid': product_internalid,
                    'product_name': lp_line.product.purchase_description,
                    'product_image': img_path,
                    'preferred_bin_name': preferred_bin_name,
                    'preferred_bin_id': preferred_bin_id,
                    'preferred_bin_onhand': preferred_bin_onhand,
                    'mpn': lp_line.product.mpn,
                    'ddn': lp_line.product.ddn,
                    'upc': lp_line.product.upc,
                    'sku': lp_line.product.sku,
                    'bin_inventory': bin_inventory,
                    'options': lp_line.options,
                    'qty_received': lp_line.qty,
                    'qty_onhand': receive_bin_onhand,
                    'qty_available': receive_bin_available,
                    'qty_remaining': qty_remaining,
                    'qty_putaway': lp_line.qty_putaway,
                    'line_ids': [lp_line.id]
                }


                lp_vals['lines'][product_internalid] = item_res


        lines = []
        for product_internalid, line_val in lp_vals['lines'].items():
            qty_remaining = line_val['qty_remaining']
            qty_received = line_val['qty_received']

            #If the line has been fully received, there is no point in showing it to them
#            if qty_remaining == 0:
 #               continue

            receive_bin_available = line_val['qty_available']
            #If the available quantity is less than the remaining qty, we can't process it all
            #allow to process what is left
            qty_underavailable = 0
            if qty_remaining > receive_bin_available:
                qty_remaining = receive_bin_available
                qty_underavailable = qty_remaining - receive_bin_available

            color = 'white'
            color_position = '0'
            if qty_received == qty_remaining:
                color = '#F37155'
                color_position = '2'
            elif qty_remaining == 0:
                color = 'lightgreen'
            elif qty_remaining > 0:
                color = 'orange'
                color_position = '3'

            line_val['color'] = color
            line_val['color_position'] = color_position
            line_val['qty_remaining'] = qty_remaining
            line_val['qty_underavailable'] = qty_underavailable
            lines.append(line_val)
            if qty_remaining > 0:
                lp_vals['show_force_complete'] = False

        lp_vals['lines'] = lines
        return lp_vals


    def force_lp_complete(self, lp_id, force_vals):
        _logger.info('Force Complete')
        lp = self.env['license.plate'].browse(lp_id)
        for product in lp.products:
            product.qty_putaway = product.qty
        lp.status = 'Putaway'
        return {'result': 'success', 'license_plate': {'status': 'Putaway'}}


    def submit_bin_putaway(self, reception_line, transfer_vals):
        """{'bin_inventory': [{'bin': 'EC5',
                              'bin_type': 'Receiving',
                              'bin_type_internalid': '3',
                              'internalid': '112596',
                              'location_internalid': '2',
                              'location_name': 'Indianapolis FC',
                              'preferred': False,
                              'qty_available': 10,
                              'qty_onhand': 10,
                              'status': '1'},
                             {'bin': '2G-54-02',
                              'bin_type': '',
                              'bin_type_internalid': '',
                              'internalid': '32325',
                              'location_internalid': '2',
                              'location_name': 'Indianapolis FC',
                              'preferred': True,
                              'qty_available': 10,
                              'qty_onhand': 10,
                              'status': '1'}],
           'color': '#F37155',
           'color_position': '2',
           'ddn': '81047-A',
           'line_ids': [32],
           'mpn': '53234696',
           'options': 'Length: 6 ft\nHeight: 34 in\nFinish: Antique Bronze',
           'preferred_bin_id': '32325',
           'preferred_bin_name': '2G-54-02',
           'preferred_bin_onhand': 10,
           'product_image': 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg',
           'product_internalid': '1263',
           'product_name': 'FE26 Traditional Adjust-a-Rail Stair Railing Panel by '
                           'Fortress Iron',
           'qty_available': 10,
           'qty_onhand': 10,
           'qty_putaway': 0,
           'qty_received': 10,
           'qty_remaining': 10,
           'qty_underavailable': 0,
           'sku': '53234696',
           'transferred_qty': '10',
           'upc': '844530005575'}"""

        """{'from_bin': '112596',
            'lp_id': 31,
            'qty': '10',
            'to_bin': '112083',
            'update_preferred_bin': False}"""

        _logger.info('Submitting Reception Line Putaway')
        line_ids = [int(l) for l in reception_line['line_ids']]

        lp_obj = self.env['license.plate']
        lp_line_obj = self.env['stock.reception.line']
        lp_lines = lp_line_obj.browse(line_ids)

        transfer_qty = float(reception_line['transferred_qty'])
        qty_committed = float(reception_line['qty_underavailable'])
        transfer_qty += qty_committed

        for line in lp_lines:
            if transfer_qty == 0:
                break
            line_qty_remaining = line.qty - line.qty_putaway
            if transfer_qty > line_qty_remaining:
                line.qty_putaway += line_qty_remaining
                transfer_qty -= line_qty_remaining
            elif line_qty_remaining >= transfer_qty:
                line.qty_putaway += transfer_qty
                transfer_qty = 0


        lp = lp_obj.browse(int(transfer_vals['lp_id']))
        lp_status = 'Putaway'
        for product in lp.products:
            if product.qty > product.qty_putaway:
                 lp_status = 'Ready for Putaway'
                 break

        lp.status = lp_status
        lp_vals = {'status': lp_status}

        """{'from_bin': {'id': 16649, 'internalid': '112083', 'name': '2C-36-01A'},
            'product': {
                'ddn': '71548-A',
               'internalid': '23279',
                'item': 'SR010616TG48-trex_deck_trns-sr-54x6-16ft-grv',
                'mpn': 'SR010616TG48',
                'preferred': True,
                'qty_available': '1068',
                'qty_onhand': '1068',
                'sku': 'SR010616TG48',
                'status': '1',
                'upc': '652835062458'
            },
            'qty': '1068',
            'to_bin': {'id': 85061, 'internalid': '113327', 'name': '2K-40-02A'}}"""
        self.submit_bin_transfer(transfer_vals)
        return {'result': 'success', 'license_plate': lp_vals}


    def license_plate_putaway_search(self, search_term=False, limit=20):
        return self.license_plate_search(search_term, limit, status='Ready for Putaway')


    def license_plate_search(self, search_term=False, limit=20, status=False):
        lp_obj = self.env['license.plate']
        lp_ids = False
        lps = False
        res = []
        if search_term:
            if status:
                lps = lp_obj.search([('name', 'ilike', search_term), ('status', '=', status)], limit=limit)
            else:
                lps = lp_obj.search([('name', 'ilike', search_term)], limit=limit)
            if not lps:
                query = "SELECT lp.id FROM license_plate lp JOIN stock_reception reception" \
                    "\nON (lp.reception = reception.id) WHERE reception.name ilike '%"+search_term+"%s'"
                if status:
                    query += "\nAND lp.status = '%s'"%status

                self.env.cr.execute(query)
                res = self.env.cr.dictfetchall()
                lp_ids = [r['id'] for r in res]

            if not lp_ids:
                query = "SELECT DISTINCT line.license_plate AS id" \
                    "\nFROM stock_reception_line line" \
                    "\nJOIN license_plate lp ON (lp.id = line.license_plate)" \
                    "\nWHERE line.create_date > current_date - interval '10 day'" \
                    "\nAND line.purchase_name ilike '%"+search_term+"%'"

                if status:
                    query += "\nAND lp.status = '%s'"%status

                self.env.cr.execute(query)
                res = self.env.cr.dictfetchall()
                lp_ids = [r['id'] for r in res]
        else:
            query = "SELECT id FROM license_plate"
            if status:
                query += "\n WHERE status = '%s'"%status
            query += "\nORDER BY write_date DESC LIMIT %s"%limit
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            lp_ids = [r['id'] for r in res]

        if lps or lp_ids:
            if lps:
                lp_ids = lps.mapped('id')

            query = "SELECT lp.id, lp.write_date, line.purchase_name AS po_name," \
                "\nline.vendor_name, lp.name AS lp_name" \
                "\nFROM license_plate lp" \
                "\nJOIN stock_reception_line line ON (lp.id = line.license_plate)"

            if len(lp_ids) > 1:
                query += "\nWHERE lp.id IN %s" % str(tuple(lp_ids))
            else:
                query += "\nWHERE lp.id = %s" % lp_ids[0]

            query += "\nGROUP BY lp.id, lp.write_date, line.purchase_name, line.vendor_name, lp.name"

            self.env.cr.execute(query)
            lp_results = self.env.cr.dictfetchall()
            res_dict = {}
            res = []
            for each in lp_results:
                if res_dict.get(each['lp_name']):
                    if each['vendor_name'] in res_dict[each['lp_name']]['vendors'].keys():
                        res_dict[each['lp_name']]['vendors'][each['vendor_name']]['purchases'].append({'name': each['po_name']})
                    else:
                        res_dict[each['lp_name']]['vendors'][each['vendor_name']] = {
                            'name': each['vendor_name'],
                            'purchases': [{'name': each['po_name']}]
                        }
                else:
                    vals = {
                        'id': each['id'],
                        'write_date': each['write_date'],
                        'name': each['lp_name'],
                        'vendors': {
                            each['vendor_name']: {
                                'name': each['vendor_name'],
                                'purchases': [{
                                    'name': each['po_name'],
                                }],
                            }
                        }
                    }
                    res_dict[each['lp_name']] = vals

            for key, value in res_dict.items():
                vendor_lines = []
                for vkey, vdata in value['vendors'].items():
                    vendor_lines.append(vdata)
                value['vendors'] = vendor_lines
                res.append(value)

            res = sorted(res, key=lambda x: x['id'], reverse=True)

        return {'search_results': res}


    def get_license_plate(self, lp_id):
        lp_obj = self.env['license.plate']
        lp = lp_obj.browse(int(lp_id))
        res = {
            'id': lp.id,
            'name': lp.name,
            'date': lp.date,
            'reception_id': lp.reception.id,
            'reception': lp.reception.name,
            'receive_bin': {'id': lp.bin.id, 'name': lp.bin.name},
            'status': lp.status,
        }

        products = []
        for product in lp.products:
            products.append({
                'id': product.id,
                'name': product.name,
                'damaged': product.damaged,
                'damage_notes': product.damage_notes,
                'qty': product.qty
            })

        lp['products'] = products
        return lp
