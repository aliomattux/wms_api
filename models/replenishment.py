from odoo import api, fields, models, SUPERUSER_ID, _

class StockReplenishment(models.Model):
    _name = 'stock.replenishment'

    create_date = fields.Datetime('Create Date')
    write_date = fields.Datetime('Write Date')
    name = fields.Char('Name')
    create_uid = fields.Many2one('res.users', 'User')
    lines = fields.One2many('stock.replenishment.line', 'replen', 'Lines')
    status = fields.Selection([
        ('cancel', 'Cancelled'),
        ('open', 'Open'),
        ('done', 'Done'),
    ], 'Status')
    replen_type = fields.Selection([
        ('demand', 'On Demand'),
        ('minmax', 'Min/Max'),
    ], 'Replen Type')


class StockReplenishmentLine(models.Model):
    _name = 'stock.replenishment.line'
    _rec_name = 'product'

    product = fields.Many2one('product', 'Product')
    to_bin = fields.Many2one('bin', 'To Bin')
    qty_to_replen = fields.Float('Qty to Replen')
    cancel_picked_remainder = fields.Boolean('Cancel Picked Remainder')
    status = fields.Selection([
        ('cancel', 'Cancelled'),
        ('open', 'Open'),
        ('picked', 'Picked'),
        ('done', 'Done'),
    ], 'Status')
    replen = fields.Many2one('stock.replenishment', 'Replen')
    create_date = fields.Datetime('Create Date')
    write_date = fields.Datetime('Write Date')
    putaway_lines = fields.One2many('stock.replenishment.line.putaway', 'plan_line', 'Putaway Lines')


class StockReplenishmentLinePutaway(models.Model):
    _name = 'stock.replenishment.line.putaway'
    _rec_name = 'pick_bin'

    plan_line = fields.Many2one('stock.replenishment.line', 'Line')
    pick_bin = fields.Many2one('bin', 'Pick Bin')
    qty_transferred = fields.Float('Qty Transferred')
    bin_transfer_internalid = fields.Char('Bin Transfer Internal ID')
    bin_transfer_name = fields.Char('Bin Transfer Name')
