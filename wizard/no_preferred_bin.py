from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime, timedelta
from odoo.exceptions import UserError
from pprint import pprint as pp


class ProductNoPreferredBin(models.TransientModel):
    _name = 'product.no.preferred.bin'
    _description = "Products without Preferred Bin"

    name = fields.Char('Name')
    products = fields.One2many('product.no.preferred.bin.product', 'wizard', 'Products', readonly=True)

    @api.model
    def default_get(self, fields):
        products = self.get_products()
        res = {
            'products': products,
        }
        return res


    def get_products(self):
        product_obj = self.env['product']
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        conn = netsuite_obj.connection(netsuite)
        sale_vals = {
            'search_id': 3437,
            'record_type': 'item',
        }

        products = []
        product_response = self.get_netsuite_search_data(conn, sale_vals)
        for each in product_response['data']:
            row = each['columns']
            product_internalid = row['internalid']['internalid']
            ddn = row.get('custitem99')
            sku = None
            product_id = product_obj.find_netsuite_integrator_product(product_internalid, sku)
            vals = {
                'product': product_id,
                'ddn': ddn,
            }

            products.append((0, 0, vals))

        return products


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


class ProductNoPreferredBinProduct(models.TransientModel):
    _name = 'product.no.preferred.bin.product'

    product = fields.Many2one('product', 'Product')
    ddn = fields.Char('DDN')
    wizard = fields.Many2one('product.no.preferred.bin', 'Wizard')
