from odoo import api, fields, models, SUPERUSER_ID, _
import logging
from pprint import pprint as pp

_logger = logging.getLogger(__name__)

class NetsuiteIntegrator(models.TransientModel):
    _inherit = 'netsuite.integrator'

    def sync_netsuite_bins(self, job):
        conn = self.connection(job.netsuite_instance)
        logger_obj = self.env['integrator.logger']

        vals = {
                'search_id': job.search_id,
                'record_type': job.record_type,
        }

        try:
            _logger.info('Downloading all Bins from Netsuite')
            response = conn.saved(vals)
        except Exception as e:
            subject = 'Could not download bin data from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

        bin_obj = self.env['bin']
        zone_obj = self.env['stock.location.zone']

        for record in response['data']:
            record = record['columns']

            internalid = record['internalid']['internalid']
            name = record['binnumber']
            location_id = record['location']['internalid']
            location_name = record['location']['name']

            vals = {
                'internalid': internalid,
                'name': name,
                'location_internalid': location_id,
                'bin_type': None,
                'bin_internalid': None,
                'zone_name': None,
                'zone_internalid': None,
            }

            if record.get('custrecord_bin_zone'):
                zone_name = record['custrecord_bin_zone']['name']
                zone_internalid = record['custrecord_bin_zone']['internalid']
                vals['zone_name'] = zone_name
                vals['zone_internalid'] = zone_internalid
                vals['zone'] = zone_obj.get_or_create_zone(zone_name, zone_internalid).id

            if record.get('custrecord_bin_type'):
                bin_type = record['custrecord_bin_type']['name']
                bin_internalid = record['custrecord_bin_type']['internalid']
                vals['bin_type'] = bin_type
                vals['bin_internalid'] = bin_internalid

            bins = bin_obj.search([('internalid', '=', internalid)])
            if bins:
                bins[0].write(vals)
                _logger.info('Updated Bin with ID: %s'%bins[0].id)
            else:
                bin = bin_obj.create(vals)
                _logger.info('Created Bin with ID: %s'%bin.id)

        return True
