from odoo import api, fields, models, SUPERUSER_ID, _, exceptions
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def submit_netsuite_receipts(self, reception_id):
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)

        reception_obj = self.env['stock.reception']
        reception = reception_obj.browse(int(reception_id))
        purchase_data = {}
        nothing_to_receive = True
        for reception_line in reception.products:
            if reception_line.license_plate.status != 'Open':
                continue

            nothing_to_receive = False
            lp_name = reception_line.license_plate.name
            purchase_internalid = reception_line.purchase_internalid
            product_internalid = reception_line.product_internalid
            bin_internalid = reception_line.license_plate.bin.internalid

            #If at least 1 line item of the PO is in the data set
            if purchase_data.get(purchase_internalid):
                if lp_name not in purchase_data[purchase_internalid]['license_plates']:
                    purchase_data[purchase_internalid]['license_plates'].append(lp_name)
                if purchase_data[purchase_internalid]['items'].get(product_internalid):
                    if lp_name not in purchase_data[purchase_internalid]['items'][product_internalid]['license_plates']:
                        purchase_data[purchase_internalid]['items'][product_internalid]['license_plates'].append(lp_name)

                    if purchase_data[purchase_internalid]['items'][product_internalid]['bins'].get(bin_internalid):
                        purchase_data[purchase_internalid]['items'][product_internalid]['bins'][bin_internalid] += reception_line.qty
                    else:
                        purchase_data[purchase_internalid]['items'][product_internalid]['bins'][bin_internalid] = reception_line.qty
                else:
                    purchase_data[purchase_internalid]['items'][product_internalid] = {
                        'ddn': reception_line.product.ddn,
                        'bins': {bin_internalid: reception_line.qty},
                        'license_plates': [lp_name]
                    }

            #PO hasnt been added to data set yet
            else:
                purchase_data[purchase_internalid] = {
                    'name': reception_line.purchase_name,
                    'items': {
                        product_internalid: {
                            'ddn': reception_line.product.ddn,
                            'bins': {bin_internalid: reception_line.qty},
                            'license_plates': [lp_name]
                       }
                    },
                    'license_plates': [lp_name]
                }

        vals = {
            'username': self.env.user.name,
            'operation': 'receive_multi_purchase_orders',
            'purchase_data': purchase_data,
        }

        if nothing_to_receive:
            return {'result': 'failure', 'error_message': ['Nothing to Receive']}

        conn = netsuite_obj.connection(netsuite, url_override=netsuite.mobile_url)
        response = conn.request(vals)
        if not response.get('success'):
            if not response.get('error_message'):
                response['error_message'] = response
            return {'result': 'failure', 'error_message': response['error_message']}

        reception.status = 'Received'
        query = "UPDATE license_plate SET status = 'Ready for Putaway' WHERE reception = %s"%str(reception.id)
        self.env.cr.execute(query)
        return {'result': 'success', 'reception': self.get_reception(reception.id)}


    def submit_bin_transfer(self, vals):
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
        _logger.info('Submit Bin Transfer')

        product_obj = self.env['product']
        bin_obj = self.env['bin']

        products = product_obj.search([('internalid', '=', vals['product']['internalid'])])
        product = products[0]

        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        conn = netsuite_obj.connection(netsuite, url_override=netsuite.mobile_url)
        memo = 'Mobile Device'
        if vals.get('memo'):
            memo = vals['memo']

        bin_vals = {
            'operation': 'move_inventory',
            'username': self.env.user.name,
            'memo': memo,
            'date': datetime.strftime(datetime.now(), '%m/%d/%Y'),
            'location': "2",
            'lines': [{
                'from_bin_id': vals['from_bin']['internalid'],
                'from_bin_text': vals['from_bin']['name'],
                'to_bin_id': vals['to_bin']['internalid'],
                'to_bin_text': vals['to_bin']['name'],
                'itemid': product.internalid,
                'item_type': product.netsuite_type,
                'update_preferred_bin': vals.get('update_preferred_bin'),
                'qty': vals['qty'],
            }],
        }

        response = conn.request(bin_vals)
        _logger.info('Netsuite Bin Transfer Response')
        return {'result': 'success', 'message': 'Bin transfer performed successfully'}

