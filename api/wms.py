from odoo import api, fields, models, SUPERUSER_ID, _
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _name = 'stock.wms'

    name = fields.Char('Name')
