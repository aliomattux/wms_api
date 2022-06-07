from odoo import api, fields, models, SUPERUSER_ID, _
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def vendor_search(self, search_term=False, limit=5):
        vendor_obj = self.env['stock.vendor']
        results = []
        if search_term:
            vendors = vendor_obj.search([('name', 'ilike', search_term)], limit=limit)
            if vendors:
                vendor_ids = vendors.mapped('id')
                query = "SELECT id, internalid, name FROM stock_vendor"
                if len(vendor_ids) > 1:
                    query += "\nWHERE id IN %s"%str(tuple(vendor_ids))
                else:
                    query += "\nWHERE id = %s" % vendor_ids[0]

                self.env.cr.execute(query)
                results = self.env.cr.dictfetchall()

        return {'search_results': results}


    def vendor_on_po_search(self, search_term=False, limit=5):
        purchase_obj = self.env['purchase.order']
        results = []
        if search_term:
            pos = purchase_obj.search([('vendor_name', 'ilike', search_term)], limit=limit)
            if pos:
                vendor_ids = pos.mapped('vendor_internalid')
                query = "SELECT id, internalid, name FROM stock_vendor"
                if len(vendor_ids) > 1:
                    query += "\nWHERE internalid IN %s"%str(tuple(vendor_ids))
                else:
                    query += "\nWHERE internalid = %s" % vendor_ids[0]

                self.env.cr.execute(query)
                results = self.env.cr.dictfetchall()

        return {'search_results': results}
