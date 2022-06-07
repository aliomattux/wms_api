from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime, timedelta
from odoo.exceptions import UserError
from pprint import pprint as pp


class ProductEmptyPreferredBin(models.TransientModel):
    _name = 'product.empty.preferred.bin'
    _description = "Products without Preferred Bin"

    name = fields.Char('Name')
    products = fields.One2many('product.empty.preferred.bin.product', 'wizard', 'Products', readonly=True)
    products_count = fields.Integer('Products Count')

    @api.model
    def default_get(self, fields):
        products = self.get_products()
        res = {
            'products': products,
            'products_count': len(products),
        }
        return res


    def get_products(self):
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        conn = netsuite_obj.connection(netsuite)
        sale_vals = {
            'search_id': 3429,
            'record_type': 'transaction',
        }

        sale_product_response = self.get_netsuite_search_data(conn, sale_vals)
        #{'id': None,
        #  'recordtype': None,
        #   'columns': {'item': {'name': 'K048-005-azk_pvr-wwhl-4x8rp-16x16g', 'internalid': '16362'}, 'formulanumeric': 308, 'formulatext': 'Stock'}}
        internalids = []

        if not sale_product_response or not sale_product_response.get('data'):
            print('Do Something')

        for each in sale_product_response['data']:
            row = each['columns']
            product_internalid = row['item']['internalid']
            if product_internalid not in internalids:
                internalids.append(product_internalid)

        if not internalids:
            print('Do Something 2')

        #  '9583': {'bin_inventory': [{'bin': 'W-T24',
        #                              'bin_type': '',
        #                              'bin_type_internalid': '',
        #                              'internalid': '112424',
        #                              'location_internalid': '2',
        #                              'location_name': 'Indianapolis FC',
        #                              'preferred': True,
        #                              'qty_available': 30,
        #                              'qty_onhand': 30,
        #                              'status': '1'}],
        #           'item_id': '9583',
        #           'location_internalid': '2',
        #           'location_name': 'Indianapolis FC',
        #           'qty_available': 30,
        #           'qty_onhand': 30}},
        product_data = self.get_product_inventory(internalids)
        if not product_data:
            raise

        product_data = product_data['data']

        product_obj = self.env['product']
        bin_obj = self.env['bin']

        replen_data = []
        for each in sale_product_response['data']:
            row = each['columns']
            product_internalid = row['item']['internalid']
            sku = None
            product_id = product_obj.find_netsuite_integrator_product(product_internalid, sku)
            qty_unfilled = row['formulanumeric']
            stock_type = row['formulatext']

            qty_preferred = 0
            qty_receiving = 0
            qty_overstock = 0
            qty_available = 0
            preferred_bin = None

            if stock_type:
                stock_type = stock_type.lower()

            product_inventory = product_data.get(product_internalid)
            if not product_inventory:
                pp(each)
                print('Oops')
                raise

            skip_product = False
            for bin in product_inventory['bin_inventory']:
                bin_name = bin.get('bin')
                bin_internalid = bin.get('internalid')
                bin_available = bin.get('qty_available')

                if bin.get('preferred'):
                    qty_preferred += bin_available

                    if qty_preferred >= qty_unfilled:
                        skip_product = True
                        break

                    preferred_bin = bin_obj.get_or_create_bin(bin_name, bin_internalid)

                elif bin.get('bin_type') == 'Receiving':
                    qty_receiving += bin_available

                else:
                    qty_overstock += bin_available

            if skip_product:
                continue

            vals = {
                'checked': False,
                'product': product_id,
                'preferred_bin': preferred_bin.id if preferred_bin else None,
                'stock_type': stock_type,
                'qty_available': qty_preferred,
                'qty_demand': qty_unfilled,
                'qty_overstock': qty_overstock,
                'qty_receiving': qty_receiving
            }

            replen_data.append((0, 0, vals))

        return replen_data


    def get_product_inventory(self, internalids):
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        url = 'https://1243222.restlets.api.netsuite.com/app/site/hosting/restlet.nl?script=617&deploy=1'
        conn = netsuite_obj.connection(netsuite, url_override=url)

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


    def get_netsuite_search_data(self, conn, vals):
        try:
       #     _logger.info('Downloading Netsuite Search Data')
            response = conn.saved(vals)
            return response

        except Exception as e:
            subject = 'Could not get all fulfillment data from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

        return False
   #     if not response or not response.get('data'):
    #        return True


class ProductEmptyPreferredBinProduct(models.TransientModel):
    _name = 'product.empty.preferred.bin.product'

    checked = fields.Boolean('Checked')
    product = fields.Many2one('product', 'Product')
    ddn = fields.Char('DDN', related="product.ddn")
    preferred_bin = fields.Many2one('bin', 'Preferred Bin')
    qty_available = fields.Char('Qty Available')
    qty_demand = fields.Char('Qty Demand')
    qty_overstock = fields.Char('Qty Overstock')
    qty_receiving = fields.Char('Qty Receiving')
    stock_type = fields.Selection([
        ('stock', 'Stock'),
        ('crossdock', 'Crossdock'),
    ], 'Stock Type', required=True)
    wizard = fields.Many2one('product.empty.preferred.bin', 'Wizard')
