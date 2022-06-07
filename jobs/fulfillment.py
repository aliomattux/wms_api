from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime
import logging
from pprint import pprint as pp
import pytz

_logger = logging.getLogger(__name__)

class NetsuiteIntegrator(models.TransientModel):
    _inherit = 'netsuite.integrator'

    def sync_item_fulfillments(self, job):
        response = False
        conn = self.connection(job.netsuite_instance)
        vals = {
            'search_id': job.search_id,
            'record_type': job.record_type,
        }

        try:
            _logger.info('Downloading item fulfillments from Netsuite')
            response = conn.saved(vals)
        except Exception as e:
            subject = 'Could not get all fulfillment data from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

        if not response or not response.get('data'):
            return True

        processed_fulfillments = self.process_fulfillment_response(response['data'], 'all')

        if processed_fulfillments:
            return self.upsert_netsuite_fields(conn, processed_fulfillments)


    def sync_deleted_item_fulfillments(self, job):
        response = False
        conn = self.connection(job.netsuite_instance)
        vals = {
            'search_id': job.search_id,
            'record_type': job.record_type,
        }

        try:
            _logger.info('Downloading Deleted fulfillments from Netsuite')
            response = conn.saved(vals)
        except Exception as e:
            print(e)
            subject = 'Could not get updated fulfillment data from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

        if not response or not response.get('data'):
            return True

        for record in response['data']:
            record = record['columns']
            name = record['name'].replace('Item Fulfillment #', '')
            query = "UPDATE stock_fulfillment SET exception_prior_status = status, netsuite_deleted = TRUE, status = 'exception', exception_acknowledged = False, exception_reason = 'Deleted from Netsuite' WHERE name = '%s' AND netsuite_status != 'Shipped' AND netsuite_deleted IS NOT TRUE" % name
            self.env.cr.execute(query)


    def process_fulfillment_response(self, response_data, sync_type):
        fulfill_obj = self.env['stock.fulfillment']
        line_obj = self.env['stock.fulfillment.line']
        type_obj = self.env['stock.fulfillment.type']

        records = {}

        #Organize the data
        fulfillment_data = []

        for record in response_data:
            record = record['columns']
            internalid = record['internalid']['internalid']
            status = record.get('statusref')

            entity = False
            if record.get('entity'):
                entity = record['entity']

            if records.get(internalid):
                if entity and not records[internalid].get('entity'):
                    records[internalid]['entity'] = entity
            else:
                records[internalid] = self.api_fulfillment_header(record)

            records[internalid]['lines'].append(record)

        limit = 100
        count = 0

        #Use data
        for internalid, record in records.items():
            count += 1
            if count >= limit:
                return fulfillment_data

            fulfillment = self.find_fulfillment_exists(internalid)
            fulfillment_vals = self.odoo_fulfillment_vals(record)

            fulfillment_created = False

            if not fulfillment:
                fulfillment_created = True
                if fulfillment_vals['netsuite_status'] == 'Shipped':
                    fulfillment_vals['status'] = 'done'
                else:
                    fulfillment_vals['status'] = 'new'

                fulfillment = fulfill_obj.create(fulfillment_vals)
              #  _logger.info('Created Fulfillment with ID: %s'%fulfillment.id)
            else:
                if fulfillment_vals['netsuite_status'] == 'Shipped':
                    fulfillment_vals['status'] = 'done'

                fulfillment.write(fulfillment_vals)
#                _logger.info('Updated Fulfillment with ID: %s'%fulfillment.id)

            fulfillment_id = fulfillment.id

            cubic_inches = 0
            cubic_feet = 0
            total_weight = 0

            fulfillment_type = False
            line_fulfillment_type = 'parcel'

            dimension_ids = []

            shipping_method = False
            shipmethod = record.get('shipmethod')
            if shipmethod:
                shipmethod_id = shipmethod['internalid']
                shipping_obj = self.env['shipping.method']
                shipping_methods = shipping_obj.search([('internalid', '=', shipmethod_id)])
                if shipping_methods:
                    shipping_method = shipping_methods[0]

            for line in record['lines']:
                line_internalid = line['lineuniquekey']
                line_qty = line.get('quantity')
                if not line_qty:
                    continue

                product, line_vals = self.odoo_fulfillment_line_vals(line, fulfillment_id)

                bin_internalid = None
                if line.get('binnumber'):
                    bin_internalid = line['binnumber']['internalid']

                fulfillment_line = self.find_fulfillment_line_exists(line_internalid, bin_internalid)
                if fulfillment_line:
                    fulfillment_line.write(line_vals)
                else:
                    fulfillment_line = line_obj.create(line_vals)

                cubic_feet += fulfillment_line.cubic_feet
                total_weight += fulfillment_line.total_weight

                if product.length >= 48:
                    line_fulfillment_type = 'long_parcel'

                #Dimensions
                if fulfillment_created:
                    for dimension in product.dimensions:
                        if dimension.id not in dimension_ids:
                            dimension_ids.append(dimension.id)

            fulfillment.cubic_feet = cubic_feet
            fulfillment.total_weight = total_weight

            if fulfillment_created:
                fulfillment.dimensions = [(6, 0, dimension_ids)]

            if shipping_method:
                if shipping_method.shipping_type == 'ltl':
                    fulfillment_type = 'ltl'

                elif shipping_method.shipping_type == 'express':
                    fulfillment_type = 'express'

            if fulfillment.support_order:
                if shipping_method.shipping_type == 'ltl':
                    fulfillment_type = 'cs_ltl'
                else:
                    fulfillment_type = 'cs_parcel'

            if fulfillment_type not in ['ltl', 'express', 'cs_parcel', 'cs_ltl']:
                fulfillment_type = line_fulfillment_type

            if shipping_method and shipping_method.shipping_type == 'local_pickup':
                fulfillment_type = 'local_pickup'

            shipping_address_1 = fulfillment.shipping_address_1
            shipping_zip = fulfillment.shipping_zip
            ship_together_fulfillments = self.find_ship_together_fulfillments(fulfillment)

            if ship_together_fulfillments:
                for ship_together_fulfillment in ship_together_fulfillments:
                    ship_together_fulfillment.exception_prior_status = ship_together_fulfillment.status
                    ship_together_fulfillment.status = 'exception'
                    ship_together_fulfillment.exception_reason = 'Ships to same address'


            types = type_obj.search([('code', '=', fulfillment_type)])
            fulfillment.fulfillment_type = types[0]

            fulfillment_data.append({
                'id': internalid,
                'type': 'itemfulfillment',
                'field': 'custbody_wm_imported',
                'value': 'T'
            })

            self.env.cr.commit()


        return fulfillment_data


    def find_ship_together_fulfillments(self, fulfillment):
        fulfillment_obj = self.env['stock.fulfillment']

        query = "SELECT fulfillment.id FROM stock_fulfillment fulfillment"
        query += "\nJOIN shipping_method ON shipping_method.id = fulfillment.shipping_method"
        query += "\nWHERE fulfillment.shipping_address_1 = '%s'"%fulfillment.shipping_address_1
        query += "\nAND fulfillment.shipping_zip = '%s'"%fulfillment.shipping_zip
        query += "\nAND fulfillment.status != 'done'"
        query += "\nAND fulfillment.netsuite_status != 'Shipped'"
        query += "\nAND shipping_method.shipping_type != 'local_pickup'"
        query += "\nAND fulfillment.exception_reason IS NULL"

        if fulfillment.shipping_method.shipping_type == 'ltl':
            query += "\nAND shipping_method.shipping_type = 'ltl'"
        else:
            query += "\nAND shipping_method.shipping_type != 'ltl'"

        self._cr.execute(query)
        fulfillment_data = self.env.cr.dictfetchall()
        fulfillment_ids = [f['id'] for f in fulfillment_data]

        if fulfillment_ids and len(fulfillment_ids) > 1:
            fulfillments = fulfillment_obj.browse(fulfillment_ids)
            return fulfillments

        return []


    def odoo_fulfillment_vals(self, record):
        #{'createdfrom': {'internalid': '14375731',
        #     'name': 'Sales Order #SO100338653929'},
        # 'custcol_custom_options': 'Option: 7-1/2" Terminal (Standard Post)\nLength: 35 ft\nSize: 1/8"',
        # 'entity': {'internalid': '7708375', 'name': '212137 Bruce Ham'},
        # 'internalid': {'internalid': '14375945', 'name': '14375945'},
        # 'item': {'internalid': '7938',
        #     'name': 'Railing : CableRail : cr_assembly : 6335-pkg-cr_assembly-lrg-35ft-18'},
        # 'lastmodifieddate': '3/15/2021 3:17 pm',
        # 'lineuniquekey': 35397851,
        # 'location': {'internalid': '2', 'name': 'Indianapolis FC'},
        # 'quantity': 16,
        # 'shipaddress': 'Bruce Ham\n60060 Wallowa Lake Hwy \nJoseph OR 97846',
        # 'shipaddress1': '60060 Wallowa Lake Hwy',
        # 'shipaddressee': 'Bruce Ham',
        # 'shipcity': 'Joseph',
        # 'shipcountry': {'internalid': 'US', 'name': 'United States'},
        # 'shipmethod': {'internalid': '996', 'name': 'FedEx 2Day\xae'},
        # 'shipstate': 'OR',
        # 'shipzip': '97846',
        # 'statusref': {'internalid': 'picked', 'name': 'Picked'},
        # 'trandate': '3/15/2021',
        # 'tranid': '22818344'}

        shipping_obj = self.env['shipping.method']
        shipping_method_internalid = False
        shipping_method_name = ''
        shipping_method_id = None

        shipmethod = record.get('shipmethod')

        if shipmethod:
            shipping_method_internalid = shipmethod['internalid']
            shipping_method_name = shipmethod['name']
            shipping_methods = shipping_obj.search([('internalid', '=', shipping_method_internalid)])
            if shipping_methods:
                shipping_method_id = shipping_methods[0].id

        address_line1 = record.get('shipaddress1')
        if address_line1:
            address_line1 = address_line1.replace("'", '').replace('"', '')
        address_line2 = record.get('shipaddress2')
        if address_line2:
            address_line2 = address_line2.replace("'", '').replace('"', '')

        address_line3 = record.get('shipaddress3')
        if address_line3:
            address_line3 = address_line3.replace("'", '').replace('"', '')

        city = record.get('shipcity')
        state = record.get('shipstate')
        country = record['shipcountry']['internalid']
        phone = record.get('shipphone')
        sale_order = record['createdfrom']['name'].replace('Sales Order #', '')
        sale_order_internalid = record['createdfrom']['internalid']

        support_order = record.get('custbody_associated_case')
        if support_order:
            support_order = True

        special_order_fulfillment = self.check_boolean(record.get('custbody_special_order_fulfillment'))

        vals = {
            'name': record.get('tranid'),
            'internalid': record['internalid']['internalid'],
            'customer_internalid': record['entity']['internalid'],
            'customer_name': record['entity']['name'],
            'shipping_method': shipping_method_id,
            'shipping_method_name': shipping_method_name,
            'shipping_method_internalid': shipping_method_internalid,
            'shipping_attention': record.get('shippingattention'),
            'shipping_addressee': record.get('shipaddressee'),
            'shipping_address_1': address_line1,
            'shipping_address_2': address_line2,
            'shipping_address_3': address_line3,
            'shipping_city': city,
            'shipping_state': state,
            'shipping_zip': record.get('shipzip'),
            'shipping_country': country,
            'shipping_phone': phone,
            'sale_order': sale_order,
            'support_order': support_order,
            'special_order_fulfillment': special_order_fulfillment,
            'sale_order_internalid': sale_order_internalid,
            'date': self.convert_fulfillment_date(record.get('trandate')),
            #'netsuite_last_modified':
            'ops_notes': record.get('custbody24'),
            'packingslip_notes': record.get('custbody6'),
            'location': record['location']['name'],
            'location_internalid': record['location']['internalid'],
            'netsuite_status': record['statusref']['name'],
        }

        #'custbody_date_fulfillment_shipped': '10/18/2021 8:30:00 am',
        if record.get('custbody_date_fulfillment_shipped'):
            shipped_value = record['custbody_date_fulfillment_shipped']
            date = datetime.strptime(shipped_value,'%m/%d/%Y %I:%M:%S %p')
            local_time = pytz.timezone("America/Chicago")
            local_datetime = local_time.localize(date, is_dst=None)
            utc_datetime = local_datetime.astimezone(pytz.utc)
            date_string = utc_datetime.strftime('%Y-%m-%d %H:%M:%S')
            vals['date_done'] = date_string
#            vals['date_done'] = datetime.strftime(date, '%Y-%m-%d')

        return vals


    def odoo_fulfillment_line_vals(self, record, fulfillment_id):
        #{'createdfrom': {'internalid': '14375731',
        #     'name': 'Sales Order #SO100338653929'},
        # 'custcol_custom_options': 'Option: 7-1/2" Terminal (Standard Post)\nLength: 35 ft\nSize: 1/8"',
        # 'entity': {'internalid': '7708375', 'name': '212137 Bruce Ham'},
        # 'internalid': {'internalid': '14375945', 'name': '14375945'},
        # 'item': {'internalid': '7938',
        #     'name': 'Railing : CableRail : cr_assembly : 6335-pkg-cr_assembly-lrg-35ft-18'},
        # 'lastmodifieddate': '3/15/2021 3:17 pm',
        # 'lineuniquekey': 35397851,
        # 'location': {'internalid': '2', 'name': 'Indianapolis FC'},
        # 'quantity': 16,
        # 'shipaddress': 'Bruce Ham\n60060 Wallowa Lake Hwy \nJoseph OR 97846',
        # 'shipaddress1': '60060 Wallowa Lake Hwy',
        # 'shipaddressee': 'Bruce Ham',
        # 'shipcity': 'Joseph',
        # 'shipcountry': {'internalid': 'US', 'name': 'United States'},
        # 'shipmethod': {'internalid': '996', 'name': 'FedEx 2Day\xae'},
        # 'shipstate': 'OR',
        # 'shipzip': '97846',
        # 'statusref': {'internalid': 'picked', 'name': 'Picked'},
        # 'trandate': '3/15/2021',
        # 'tranid': '22818344'}

        qty = float(record.get('quantity'))
        cubic_feet = 0
        total_weight = 0

        product_internalid = record['item']['internalid']
        sku = record['custitem36']
        ddn = record['custitem99']

        product_obj = self.env['product']
        product_id = product_obj.find_netsuite_integrator_product(product_internalid, sku)
        product = product_obj.browse(product_id)
        cubic_feet = round(product.cubic_feet * qty, 2)
        total_weight = round(product.weight * qty, 2)

        bin_obj = self.env['bin']
        if not record.get('binnumber'):
             record['binnumber'] = {'name': 'No Bin', 'internalid': 0}

        bin_name = record['binnumber']['name']
        bin_internalid = record['binnumber']['internalid']
        bin = bin_obj.get_or_create_bin(bin_name, bin_internalid)

        vals = {
            'fulfillment_internalid': record['internalid']['internalid'],
            'fulfillment_line_internalid': record.get('lineuniquekey'),
            'bin': bin.id,
            'sku': sku,
            'ddn': ddn,
            'bin_qty': qty,
            'bin_name': bin_name,
            'bin_internalid': bin_internalid,
            'options': record.get('custcol_custom_options'),
            'product_internalid': product_internalid,
            'product': product_id,
            'cubic_feet': cubic_feet,
            'total_weight': total_weight,
            'fulfillment': fulfillment_id
        }

        return (product, vals)


    def convert_fulfillment_date(self, value):
        if value:
            d = datetime.strptime(value, '%m/%d/%Y')
            return datetime.strftime(d, '%Y-%m-%d')
        return value


    def find_fulfillment_exists(self, internalid):
        fulfill_obj = self.env['stock.fulfillment']
        fulfillments = fulfill_obj.search([('internalid', '=', internalid)])
        if fulfillments:
            return fulfillments[0]
        return False


    def find_fulfillment_line_exists(self, internalid, bin_internalid):
        fulfill_line_obj = self.env['stock.fulfillment.line']
        lines = fulfill_line_obj.search([('fulfillment_line_internalid', '=', internalid), ('bin_internalid', '=', bin_internalid)])
        if lines:
            return lines[0]
        return False


    def api_fulfillment_header(self, record):
        record['lines'] = []
        return record


    def check_boolean(self, value):
        if not value:
            return False
        if value == 'T':
            return True
        return False
