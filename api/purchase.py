from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def purchase_order_search(self, search_term=False, vendor_id=False, limit=20):
        purchase_obj = self.env['purchase.order']
        res = []
        filters = []
        purchase_ids = False
        purchases = False
        if search_term or vendor_id:
            if search_term:
                filters.append(('name', 'ilike', search_term))

            if vendor_id:
                filters.append(('vendor_internalid', '=', vendor_id))

            purchases = purchase_obj.search(filters, limit=limit)
            if not purchases and not vendor_id:
                filters =  [('vendor_name', 'ilike', search_term)]
                purchases = purchase_obj.search(filters, limit=limit)

        else:
            query = "SELECT id FROM purchase_order ORDER BY write_date, create_date DESC LIMIT %s"%limit
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            purchase_ids = [r['id'] for r in res]

        if purchases or purchase_ids:
            if purchases:
                purchase_ids = purchases.mapped('id')

            query = "SELECT purchase.id, purchase.name, purchase.date, purchase.vendor_name, purchase.vendor_internalid, " \
            "purchase.receive_by FROM purchase_order purchase"
            if len(purchase_ids) > 1:
                query += "\nWHERE purchase.id IN %s" % str(tuple(purchase_ids))
            else:
                query += "\nWHERE purchase.id = %s" % purchase_ids[0]

            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()

        return {'search_results': res}


    def get_purchase(self, purchase_id):
        purchase_obj = self.env['purchase.order']
        purchase = purchase_obj.browse(int(purchase_id))
        purchase_id = purchase.id
        res = {
            'id': purchase_id,
            'internalid': purchase.internalid,
            'name': purchase.name,
            'vendor_name': purchase.vendor_name,
            'vendor_internalid': purchase.vendor_internalid,
            'date': datetime.strftime(purchase.date, '%m-%d-%y'),
            'receive_by': datetime.strftime(purchase.receive_by, '%m-%d-%y'),
            'ops_notes': purchase.ops_notes,
            'location': purchase.location,
        }

        lines = []
        for line in purchase.lines:
            lines.append({
                'description': line.description,
                'product_internalid': line.product_internalid,
                'purchase_internalid': purchase.internalid,
                'po_line_internalid': line.po_line_internalid,
                'qty': line.qty,
                'qty_remaining': line.qty_remaining,
                'qty_remaining_unreceived': line.qty_remaining,
                'options': line.options or None
            })

        res['lines'] = lines
        return res


    def get_purchase_orders_reception_summary(self, purchases):
        master_data = {}
        for purchase in purchases:
            for po_line in purchase.lines:
                product_internalid = po_line.product_internalid
                product = po_line.product
                if master_data.get(product_internalid):
                    master_data[product_internalid]['qty_remaining'] += po_line.qty_remaining
                    master_data[product_internalid]['qty_remaining_unreceived'] += po_line.qty_remaining
                    po_line_found = False
                    for product_po_line in master_data[product_internalid]['purchase_lines']:
                        if product_po_line['purchase_internalid'] == purchase.internalid:
                            po_line_found = True
                            if po_line.po_line_internalid not in product_po_line['po_line_internalids']:
                                product_po_line['qty_remaining'] += po_line.qty_remaining
                                product_po_line['qty_remaining_unreceived'] += po_line.qty_remaining
                                product_po_line['po_line_internalids'].append(po_line.po_line_internalid)
                            break

                    if not po_line_found:
                        master_data[product_internalid]['purchase_lines'].append({
                            'purchase_internalid': purchase.internalid,
                            'purchase_name': purchase.name,
                            'vendor_name': purchase.vendor_name,
                            'po_line_internalids': [po_line.po_line_internalid],
                            'qty_remaining':  po_line.qty_remaining,
                            'qty_remaining_unreceived': po_line.qty_remaining,
                            'qty_received': 0,
                            'lp_lines': [],
                        })

                else:
                    img_path = product.img_path
                    img_no_selection = 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg'
                    if img_path == 'https://www.decksdirect.com/media/catalog/productno_selection' or not img_path:
                        img_path = img_no_selection

                    master_data[product_internalid] = {
                        'product_name': product.purchase_description or po_line.description,
                        'purchase_description':  po_line.description,
                        'product_image': img_path,
                        'ddn': product.ddn,
                        'upc': product.upc,
                        'mpn': product.mpn,
                        'product_id': product.id,
                        'sku': product.sku,
                        'options': po_line.options,
                        'filter_size': po_line.product.filter_size,
                        'filter_weight': po_line.product.filter_weight,
                        'qty_remaining': po_line.qty_remaining,
                        'qty_remaining_unreceived': po_line.qty_remaining,
                        'qty_received': 0,
                        'purchase_lines': [
                            {'purchase_internalid': purchase.internalid,
                             'purchase_name': purchase.name,
                             'vendor_name': purchase.vendor_name,
                             'qty_remaining':  po_line.qty_remaining,
                             'qty_remaining_unreceived': po_line.qty_remaining,
                             'po_line_internalids': [po_line.po_line_internalid],
                             'qty_received': 0,
                             'lp_lines': [],
                        }],
                    }

        return master_data
