from odoo import api, fields, models, SUPERUSER_ID, _

class Bin(models.Model):
    _name = 'bin'

    internalid = fields.Char('Internal ID')
    name = fields.Char('Name')
    location_name = fields.Char('Location Name')
    location_internalid = fields.Char('Location Internal ID')
    bin_type = fields.Char('Bin Type')
    bin_internalid = fields.Char('Bin Internal ID')


    def get_or_create_bin(self, bin_name, bin_internalid):
        bins = self.search([('internalid', '=', bin_internalid)])
        if not bins:
            bins = self.search([('name', '=', bin_name)])
        if bins:
           return bins[0]

        return self.create({'name': bin_name, 'internalid': bin_internalid})
