from odoo import api, fields, models, SUPERUSER_ID, _

class LicensePlate(models.Model):
    _name = 'license.plate'

    name = fields.Char('Name', index=True)
    date = fields.Date('Date')
    products = fields.One2many('stock.reception.line', 'license_plate', 'Products')
    reception = fields.Many2one('stock.reception', 'Reception')
    bin = fields.Many2one('bin', 'Receiving Bin', index=True)
    status = fields.Selection([
            ('Open', 'Open'),
            ('Ready for Putaway', 'Ready for Putaway'),
            ('Putaway', 'Putaway')], 'Status', default='Open', index=True
    )
