from odoo import api, fields, models, SUPERUSER_ID, _
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def product_search(self, search_term, limit):
        product_obj = self.env['product']
        res = []
        products = product_obj.search(['|','|','|',
            ('ddn', 'ilike', search_term),
            ('sku', 'ilike', search_term),
            ('name', 'ilike', search_term),
            ('mpn', 'ilike', search_term
        )], limit=limit)

        if products:
            product_ids = products.mapped('id')
            query = "SELECT COALESCE(product.ddn, 'No DDN') AS ddn, COALESCE(product.sku, 'No SKU') AS sku, product.name," \
                """\nproduct.img_path, product.id AS id, product.upc, product.mpn, product.internalid""" \
                "\nFROM product"

            if len(product_ids) > 1:
                query += "\nWHERE product.id IN %s" % str(tuple(product_ids))
            else:
                query += "\nWHERE product.id = %s" % product_ids[0]

            query += "\nLIMIT %s"%limit

            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()

        new_res = []
        for each in res:
            img_path = each.get('img_path')
            img_no_selection = 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg'
            if img_path == 'https://www.decksdirect.com/media/catalog/productno_selection' or not img_path:
                each['img_path'] = img_no_selection

            new_res.append(each)

        return {'search_results': new_res}


    def get_one_product_inventory(self, product_id):
        product_obj = self.env['product']
        product = product_obj.browse(int(product_id))
        name = product.name

        img_path = product.img_path
        img_no_selection = 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg'
        if img_path == 'https://www.decksdirect.com/media/catalog/productno_selection' or not img_path:
            img_path = img_no_selection

        productData = {
                'name': name or False,
                'sku': product.sku,
                'ddn': product.ddn,
                'mpn': product.mpn,
                'img_path': img_path,
                'internalid': product.internalid,
                'bin_inventory': [],
        }

        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        conn = netsuite_obj.connection(netsuite, url_override=netsuite.mobile_url)
        vals = {
            'operation': 'get_multi_inventory',
            'product_ids': [product.internalid],
        }

        response = conn.request(vals)
        """{'data': {'17852': {'bin_inventory': [{'bin': '2D-34-01',
                                       'bin_type': '',
                                       'bin_type_internalid': '',
                                       'internalid': '30354',
                                       'location_internalid': '2',
                                       'location_name': 'Indianapolis FC',
                                       'preferred': True,
                                       'qty_available': '101',
                                       'qty_onhand': '101',
                                       'status': '1'}],
                    'item_id': '17852'}},
            'error_message': False,
            'success': True}"""
        if response.get('data') and response['data'].get(product.internalid):
            productData.update(response['data'][product.internalid])

        return productData


    def get_multi_product_inventory(self, internalids):
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        conn = netsuite_obj.connection(netsuite, url_override=netsuite.mobile_url)

        vals = {
            'operation': 'get_multi_inventory',
            'product_ids': internalids,
        }

        response = conn.request(vals)

        """{'data': {'17852': {'bin_inventory': [{'bin': '2D-34-01',
                                       'bin_type': '',
                                       'bin_type_internalid': '',
                                       'internalid': '30354',
                                       'location_internalid': '2',
                                       'location_name': 'Indianapolis FC',
                                       'preferred': True,
                                       'qty_available': '101',
                                       'qty_onhand': '101',
                                       'status': '1'}],
                    'item_id': '17852'}},
            'error_message': False,
            'success': True}"""

        return response


    def get_product(self, product_id):
        product_obj = self.env['product']
        product = product_obj.browse(int(product_id))
        name = product.name

        img_path = product.img_path
        img_no_selection = 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg'
        if img_path == 'https://www.decksdirect.com/media/catalog/productno_selection' or not img_path:
            img_path = img_no_selection

        productData = {
                'name': name or False,
                'sku': product.sku,
                'ddn': product.ddn,
                'mpn': product.mpn,
                'img_path': img_path,
                'internalid': product.internalid,
                'qty_available': None,
                'qty_onhand': None,
                'bin_inventory': [],
                'adjustments': []
        }

        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        url = 'https://1243222.restlets.api.netsuite.com/app/site/hosting/restlet.nl?script=617&deploy=1'
        conn = netsuite_obj.connection(netsuite, url_override=url)
        vals = {
            'operation': 'get_multi_inventory',
            'product_ids': [product.internalid],
        }

        response = conn.request(vals)
        """{'data': {'17852': {'bin_inventory': [{'bin': '2D-34-01',
                                       'bin_type': '',
                                       'bin_type_internalid': '',
                                       'internalid': '30354',
                                       'location_internalid': '2',
                                       'location_name': 'Indianapolis FC',
                                       'preferred': True,
                                       'qty_available': '101',
                                       'qty_onhand': '101',
                                       'status': '1'}],
                    'item_id': '17852'}},
            'error_message': False,
            'success': True}"""
        if response.get('data') and response['data'].get(product.internalid):
            productData.update(response['data'][product.internalid])

        return productData


    def get_product_exists(self, product_string):
        self.env.cr.execute("SELECT id FROM product WHERE LOWER(ddn) = LOWER('%s')"%product_string)
        res = self.env.cr.fetchone()
        if not res:
            self.env.cr.execute("SELECT id FROM product WHERE LOWER(sku) = LOWER('%s')"%product_string)
            self.env.cr.execute(query)
            res = self.env.cr.fetchone()

        if not res:
            return False

        return res[0]
