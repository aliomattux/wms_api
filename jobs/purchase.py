from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class NetsuiteIntegrator(models.TransientModel):
    _inherit = 'netsuite.integrator'

    def sync_pending_purchase_orders(self, job):
        response = False
        conn = self.connection(job.netsuite_instance)
        vals = {
                'search_id': job.search_id,
                'record_type': job.record_type,
        }

        try:
            _logger.info('Downloading all pending pos from Netsuite')
            response = conn.saved(vals)
        except Exception as e:
            subject = 'Could not get all po data data from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

        if not response or not response.get('data'):
            return True

        return self.process_po_response(response['data'], 'all')


    def sync_updated_purchase_orders(self, job):
        response = False
        conn = self.connection(job.netsuite_instance)
        vals = {
                'search_id': job.search_id,
                'record_type': job.record_type,
        }

        try:
            _logger.info('Downloading all updated pos from Netsuite')
            response = conn.saved(vals)
        except Exception as e:
            subject = 'Could not get updated po data data from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

        if not response or not response.get('data'):
            return True

        return self.process_po_response(response['data'], 'update')


    def process_po_response(self, response_data, sync_type):
        po_obj = self.env['purchase.order']
        line_obj = self.env['purchase.order.line']
        records = {}

        #Organize the data
        all_pos = []
        acceptedStatuses = [
            'Pending Receipt',
            'Partially Received',
            'Pending Billing/Partially Received',
        ]

        ignored_internalids = []

        if sync_type == 'all':
            query = "SELECT internalid FROM purchase_order"
            self.env.cr.execute(query)
            query_results = self.env.cr.dictfetchall()
            all_pos = [res['internalid'] for res in query_results]

        for record in response_data:
            record = record['columns']
            internalid = record['internalid']['internalid']
            status = record.get('statusref')
            if internalid in ignored_internalids:
                continue

            #If the PO is imported but the status is not applicable
            #Delete the PO immediately to prevent processing.
            if status and status['name'] not in acceptedStatuses:
                self.delete_one_po(internalid)
                ignored_internalids.append(internalid)
                continue

            entity = False
            if record.get('entity'):
                entity = record['entity']

            if records.get(internalid):
                if entity and not records[internalid].get('entity'):
                    records[internalid]['entity'] = entity
            else:
                records[internalid] = self.api_po_header(record)

            records[internalid]['lines'].append(record)

        #Use data
        for internalid, record in records.items():
            po = self.find_po_exists(internalid)
            po_vals = self.odoo_po_vals(record)

            line_unique_keys = []
            if not po:
                po = po_obj.create(po_vals)
 #               _logger.info('Created PO with ID: %s'%po.id)
            else:
                po.write(po_vals)
#                _logger.info('Updated PO with ID: %s'%po.id)

            po_id = po.id
            for line in record['lines']:
                line_internalid = line['lineuniquekey']
                #If there is no qty or no qty left to receive, it is skipped
                qty = float(line.get('quantity', 0))
                if not qty:
                    continue

                qty_received = float(line.get('quantityshiprecv'))
                qty_remaining = round(qty - qty_received, 1)
                if qty_remaining < 1:
                    continue

                line_unique_keys.append(str(line_internalid))
                line_vals = self.odoo_po_line_vals(line, po_id)
                line = self.find_po_line_exists(line_internalid)
                if line:
                    line.write(line_vals)
                else:
                    line = line_obj.create(line_vals)

            self.reconcile_po_lines(internalid, line_unique_keys)

        #If we are syncing all PO's we want to remove ones not in the list
        if sync_type == 'all':
            diff_pos = list(set(all_pos) - set(records.keys()))
            for po in diff_pos:
                self.delete_one_po(po)

        return True


    def reconcile_po_lines(self, po_internalid, line_ids):
        query = "DELETE FROM purchase_order_line WHERE po_internalid = '%s' AND " \
            "po_line_internalid NOT IN %s"%(po_internalid, str(line_ids).replace('[', '(').replace(']', ')'))
        self.env.cr.execute(query)


    def delete_one_po(self, internalid):
        _logger.info('Deleting PO: %s'%internalid)
        query = "DELETE FROM purchase_order_line WHERE po_internalid = '%s'"%internalid
        self.env.cr.execute(query)
        query = "DELETE FROM purchase_order WHERE internalid = '%s'"%internalid
        self.env.cr.execute(query)
        return True


    def odoo_po_vals(self, record):
        #{'duedate': '3/10/2021',
        # 'statusref': {'internalid': 'pendingBilling', 'name': 'Pending Bill'},
        # 'entity': {'internalid': '1259754',
        #              'name': 'Sure Drive USA'},
        #  'internalid': {'internalid': u'14350856','name': '14350856'},
        #  'location': {'internalid': u'2', 'name': 'Indianapolis FC'},
        #  'lineuniquekey': 32022240,
        #  'quantityshiprecv': 0,
        #  'custbody24': 'some message',
        #  'trandate': '3/10/2021',
        #  'tranid': 'DD78055'}
        vals = {
            'name': record.get('tranid'),
            'internalid': record['internalid']['internalid'],
            'vendor_name': record['entity']['name'],
            'vendor_internalid': record['entity']['internalid'],
            'date': self.convert_po_date(record.get('trandate')),
            'receive_by': self.convert_po_date(record.get('duedate')),
            'ops_notes': record.get('custbody24'),
            'location': record['location']['name'],
            'location_internalid': record['location']['internalid']
        }

        return vals


    def odoo_po_line_vals(self, record, po_id):
        #{'duedate': '3/10/2021',
        # 'entity': {'internalid': '1259754',
        #              'name': 'Sure Drive USA'},
        #  'internalid': {'internalid': u'14350856','name': '14350856'},
        #  'location': {'internalid': u'2', 'name': 'Indianapolis FC'},
        #  'item': {'internalid': '11035',
        #      'name': 'Lighting : Aurora : aur_iris : JLA7058-aur_iris-5916-blk'},
        #  'lineuniquekey': 32022240,
        #  'quantityshiprecv': 0,
        #  'custbody24': 'some message',
        #  'custcol_custom_options': 'Height: 42 in\n'
        #      'Type: Square Balusters\n'
        #      'Finish: Classic White',
        #  'trandate': '3/10/2021',
        #  'tranid': 'DD78055'}
        qty = float(record.get('quantity'))
        qty_received = float(record.get('quantityshiprecv'))
        qty_remaining = round(qty - qty_received, 1)
        product_internalid = record['item']['internalid']
        products = self.env['product'].search([('internalid', '=', product_internalid)])
        vals = {
            'po_internalid': record['internalid']['internalid'],
            'po_line_internalid': record.get('lineuniquekey'),
            'qty_received': qty_received,
            'qty': qty,
            'qty_remaining': qty_remaining,
            'options': record.get('custcol_custom_options'),
            'product_internalid': product_internalid,
            'description': record.get('memo'),
            'purchase': po_id
        }

        if products:
            vals['product'] = products[0].id

        return vals


    def convert_po_date(self, value):
        if value:
            d = datetime.strptime(value, '%m/%d/%Y')
            return datetime.strftime(d, '%Y-%m-%d')
        return value


    def find_po_exists(self, internalid):
        po_obj = self.env['purchase.order']
        pos = po_obj.search([('internalid', '=', internalid)])
        if pos:
            return pos[0]
        return False


    def find_po_line_exists(self, internalid):
        po_line_obj = self.env['purchase.order.line']
        lines = po_line_obj.search([('po_line_internalid', '=', internalid)])
        if lines:
            return lines[0]
        return False


    def api_po_header(self, record):
        record['lines'] = []
        return record


    def check_boolean(self, value):
        if not value:
            return False
        if value == 'T':
            return True
        return False
