from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime

class StockFulfillment(models.Model):
    _name = 'stock.fulfillment'

    name = fields.Char('Name')
    internalid = fields.Char('Internal ID', index=True)
    netsuite_last_modified = fields.Datetime('Netsuite Last Modified')
    customer_internalid = fields.Char('Vendor Internal ID', index=True)
    customer_name = fields.Char('Customer Name')
    shipping_method = fields.Many2one('shipping.method', 'Shipping Method')
    shipping_method_name = fields.Char('Shipping Method')
    shipping_method_internalid = fields.Char('Shipping Method Internal ID')
    shipping_attention = fields.Char('Attention')
    shipping_addressee = fields.Char('Addressee')
    shipping_address_1 = fields.Char('Address 1')
    shipping_address_2 = fields.Char('Address 2')
    shipping_address_3 = fields.Char('Address 3')
    shipping_city = fields.Char('City')
    shipping_state = fields.Char('State')
    shipping_country = fields.Char('Country')
    shipping_phone = fields.Char('Phone')
    shipping_zip = fields.Char('Zip')
    support_order = fields.Boolean('Support Order')
    special_order_fulfillment = fields.Boolean('Special Order Fulfillment')
    sale_order = fields.Char('Sales Order #')
    sale_order_internalid = fields.Char('Sales Order Internal ID')
    date = fields.Date('Fulfillment Date')
    date_done = fields.Datetime('Date Shipped')
    netsuite_deleted = fields.Boolean('Netsuite Deleted')
    ops_notes = fields.Text('Ops Notes')
    packingslip_notes = fields.Text('Packingslip Notes')
    netsuite_status = fields.Selection([
        ('Picked', 'Picked'),
        ('Packed', 'Packed'),
        ('Shipped', 'Shipped')], 'Netsuite Ship Status')
    exception_reason = fields.Char('Exception Reason')
    exception_acknowledged = fields.Boolean('Exception Acknowledged')
    exception_acknowledged_by = fields.Many2one('res.users', 'Exception Acknowledged By')
    exception_acknowledged_datetime = fields.Datetime('Exception Acknowledged Date/Time')
    exception_prior_status = fields.Selection([
        ('deleted', 'Deleted'),
        ('new', 'New'),
        ('waved', 'Waved'),
        ('printed', 'Printed'),
        ('picked', 'Picked'),
        ('exception', 'Exception'),
        ('done', 'Shipped'),
        ], 'Status')
    status = fields.Selection([
        ('deleted', 'Deleted'),
        ('new', 'New'),
        ('waved', 'Waved'),
        ('printed', 'Printed'),
        ('picked', 'Picked'),
        ('exception', 'Exception'),
        ('done', 'Shipped'),
        ], 'Status')
    printed_date = fields.Datetime('Printed Date')
    cubic_feet = fields.Float('Cubic Feet')
    total_weight = fields.Float('Total Weight')
    location = fields.Char('Location')
    location_internalid = fields.Char('Location Internal ID')
    lines = fields.One2many('stock.fulfillment.line', 'fulfillment', 'Lines')

    _sql_constraints = [
        ('internalid_uniq', 'unique(internalid)', 'Internal ID must be unique!'),
    ]

    def acknowledge_fulfillment(self):
        for record in self:
            record.exception_acknowledged = True


    def write(self, vals):
        if vals.get('exception_acknowledged'):
            vals['exception_acknowledged_by'] = self.env.uid
            vals['exception_acknowledged_datetime'] = datetime.utcnow()

            for picking in self:
                if picking.netsuite_deleted:
                    picking.status = 'deleted'
                else:
                    if picking.exception_prior_status == 'exception':
                        picking.status = 'new'
                    else:
                        picking.status = picking.exception_prior_status or 'new'

        res = super(StockFulfillment, self).write(vals)
        return res


class StockFulfillmentLine(models.Model):
    _name = 'stock.fulfillment.line'

    fulfillment = fields.Many2one('stock.fulfillment', 'Fulfillment', ondelete="cascade", required=True)
    description = fields.Char('Description')
    product_internalid = fields.Char('Product Internal ID', index=True)
    product = fields.Many2one('product', 'Product')
    sku = fields.Char('SKU')
    ddn = fields.Char('DDN')
    cubic_feet = fields.Float('Cubic Feet')
    total_weight = fields.Float('Total Weight')
    fulfillment_line_internalid = fields.Char('Fulfillment Line Internal ID', index=True)
    fulfillment_internalid = fields.Char('Fulfillment Internal ID')
    qty = fields.Float('Total Qty')
    bin = fields.Many2one('bin', 'Bin')
    bin_name = fields.Char('Bin')
    bin_internalid = fields.Char('Bin Internal ID')
    bin_qty = fields.Float('Bin Qty')
    options = fields.Char('Options')
