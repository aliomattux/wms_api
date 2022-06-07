from odoo import api, fields, models, SUPERUSER_ID, _
import logging

_logger = logging.getLogger(__name__)

class NetsuiteIntegrator(models.TransientModel):
    _inherit = 'netsuite.integrator'

    def sync_vendors(self, job):
        conn = self.connection(job.netsuite_instance)
        vals = {
                'search_id': job.search_id,
                'record_type': job.record_type,
        }
        try:
            _logger.info('Downloading all vendors from Netsuite')
            response = conn.saved(vals)
        except Exception as e:
            subject = 'Could not get all vendors from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

        return self.process_vendor_response(response['data'])


    def get_netsuite_integrator_vendor(self, internalid=False, name=False):
        vendor_obj = self.env['stock.vendor']
        if internalid:
            vendor_ids = vendor_obj.search([('internalid', '=', internalid)])
            if vendor_ids:
                return vendor_ids[0]
        if name:
            query = "SELECT id FROM product WHERE LOWER(name) = LOWER('%s')"%name
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            if res:
                return res[0]['id']

        return False


    def process_vendor_response(self, response_data):

        vendor_obj = self.env['stock.vendor']
        for record in response_data:
            #{'companyname': 'Zopim',
            #  'internalid': {'internalid': '955024', 'name': '955024'}
            record = record['columns']
            id = record['internalid']['internalid']
            name = record.get('companyname')
            if not name:
                continue
            vendors = vendor_obj.search([('internalid', '=', id)])
            if vendors:
                vendors[0].write({'name': name})
            else:
                vendor = vendor_obj.create({'name': name, 'internalid': id})

            #{'duedate': '3/10/2021',
            # 'entity': {'internalid': '1259754',
            #              'name': 'Sure Drive USA'},
            #  'internalid': {'internalid': u'14350856','name': '14350856'},
            #  'location': {'internalid': u'2', 'name': 'Indianapolis FC'},
            #  'quantityshiprecv': 0,
            #  'custbody24': 'some message',
            #  'trandate': '3/10/2021',
            #  'tranid': 'DD78055'}

#            internalid = record['internalid']['internalid']

        return True
