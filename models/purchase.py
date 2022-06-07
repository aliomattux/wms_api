from odoo import api, fields, models, SUPERUSER_ID, _

class PurchaseOrder(models.Model):
    _name = 'purchase.order'

    name = fields.Char('Name')
    internalid = fields.Char('Internal ID', index=True)
    vendor_name = fields.Char('Vendor Name')
    vendor_internalid = fields.Char('Vendor Internal ID', index=True)
    date = fields.Date('Date')
    receive_by = fields.Date('Receive By')
    ops_notes = fields.Text('Ops Notes')
    location = fields.Char('Location')
    location_internalid = fields.Char('Location Internal ID')
    lines = fields.One2many('purchase.order.line', 'purchase', 'Lines')


class PurchaseOrderLine(models.Model):
    _name = 'purchase.order.line'

    purchase = fields.Many2one('purchase.order', 'Purchase')
    po_internalid = fields.Char('Purchase Internal ID', index=True)
    description = fields.Char('Description')
    product = fields.Many2one('product', 'Product')
    product_internalid = fields.Char('Product Internal ID', index=True)
    po_line_internalid = fields.Char('PO Line Internal ID', index=True)
    qty = fields.Float('Qty')
    qty_received = fields.Float('Qty Received')
    qty_remaining = fields.Float('Qty Remaining')
    options = fields.Char('Options')
