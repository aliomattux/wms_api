from odoo import api, fields, models, SUPERUSER_ID, _

class StockVendor(models.Model):
    _name = 'stock.vendor'

    name = fields.Char('Name')
    internalid = fields.Char('Internal ID', index=True)
