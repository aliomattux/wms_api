from odoo import api, fields, models, SUPERUSER_ID, _

class StockReception(models.Model):
    _name = 'stock.reception'

    name = fields.Char('Name')
    date = fields.Date('Date')
    status = fields.Selection([
            ('Closed', 'Closed'),
            ('Open', 'Open'),
            ('Received', 'Received')], 'Status', default="Open"
    )
    lp_count = fields.Float('LP Count')
    notes = fields.Text('Notes')
    products = fields.One2many('stock.reception.line', 'reception', 'Products')
    purchase_orders = fields.Many2many('purchase.order', 'reception_purchase_order_rel', \
        'reception_id', 'purchase_id', 'Purchase Orders'
    )


class StockReceptionLine(models.Model):
    _name = 'stock.reception.line'

    reception = fields.Many2one('stock.reception', 'Reception', index=True)
    vendor_name = fields.Char('Vendor Name')
    damaged = fields.Boolean('Damaged')
    damage_notes = fields.Text('Damage Notes')
    product = fields.Many2one('product', 'Product')
    product_internalid = fields.Char('Product Internal ID')
    qty = fields.Float('Qty')
    qty_putaway = fields.Float('Qty Putaway')
    options = fields.Char('Options')
    purchase_internalid = fields.Char('Purchase Internal ID', required=True, index=True)
    purchase_name = fields.Char('Purchase Name', index=True)
    license_plate = fields.Many2one('license.plate', 'License Plate', index=True)
