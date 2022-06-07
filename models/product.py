from odoo import api, fields, models, SUPERUSER_ID, _
from pprint import pprint as pp

class Product(models.Model):
    _inherit = 'product'

    def name_get(self):
        if self._context.get('ddn_name'):
            res = []
            for product in self:
                val = product.ddn
                res.append((product.id, val))
            return res
        return super(Product, self).name_get()
