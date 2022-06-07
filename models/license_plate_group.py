from odoo import api, fields, models, SUPERUSER_ID, _

class LicensePlateGroup(models.Model):
    _name = 'license.plate.group'

    name = fields.Char('Name', index=True)
    date = fields.Date('Date')
    license_plates = fields.Many2many('license.plate', 'license_plate_group_rel', \
        'group_id', 'lp_id', 'License Plates'
    )
