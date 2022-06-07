from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def reception_search(self, search_term=False, limit=20):
        reception_obj = self.env['stock.reception']
        receptions = False
        reception_ids = False
        res = []
        if search_term:
            receptions = reception_obj.search([('name', 'ilike', search_term)], limit=limit)
            if not receptions:
                query = "SELECT DISTINCT reception AS id FROM license_plate WHERE name ilike '%"+search_term+"%'"
                self.env.cr.execute(query)
                res = self.env.cr.dictfetchall()
                reception_ids = [r['id'] for r in res]
            if not reception_ids:
                query = "SELECT DISTINCT reception AS id FROM stock_reception_line" \
                    "\nWHERE create_date > current_date - interval '10 day'" \
                    "\nAND purchase_name ilike '%"+search_term+"%'"

                self.env.cr.execute(query)
                res = self.env.cr.dictfetchall()
                reception_ids = [r['id'] for r in res]
        else:
            query = "SELECT id FROM stock_reception ORDER BY write_date DESC LIMIT %s"%20
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            reception_ids = [r['id'] for r in res]

        if receptions or reception_ids:
            if receptions:
                reception_ids = receptions.mapped('id')

            query = "SELECT reception.id, reception.write_date, line.purchase_name AS po_name," \
                "\nline.vendor_name, reception.name, reception.status" \
                "\nFROM stock_reception reception" \
                "\nLEFT OUTER JOIN stock_reception_line line ON (reception.id = line.reception)" \

            if len(reception_ids) > 1:
                query += "\nWHERE reception.id IN %s" % str(tuple(reception_ids))
            else:
                query += "\nWHERE reception.id = %s" % reception_ids[0]

            query += "\nGROUP BY reception.id, reception.write_date, line.purchase_name, line.vendor_name, reception.name, reception.status"
            query += "\n ORDER BY reception.write_date DESC"
            self.env.cr.execute(query)
            reception_results = self.env.cr.dictfetchall()
            res_dict = {}
            res = []
            for each in reception_results:
                if res_dict.get(each['name']):
                    if each['vendor_name'] in res_dict[each['name']]['vendors'].keys():
                        res_dict[each['name']]['vendors'][each['vendor_name']]['purchases'].append({'name': each['po_name']})
                    else:
                        res_dict[each['name']]['vendors'][each['vendor_name']] = {
                            'name': each['vendor_name'],
                            'purchases': [{'name': each['po_name']}]
                        }
                else:
                    vals = {
                        'id': each['id'],
                        'status': each['status'],
                        'write_date': each['write_date'],
                        'name': each['name'],
                        'vendors': {
                            each['vendor_name']: {
                                'name': each['vendor_name'],
                                'purchases': [{
                                    'name': each['po_name'],
                                }],
                            }
                        }
                    }
                    res_dict[each['name']] = vals

            for key, value in res_dict.items():
                vendor_lines = []
                for vkey, vdata in value['vendors'].items():
                    vendor_lines.append(vdata)
                value['vendors'] = vendor_lines
                res.append(value)

            res = sorted(res, key=lambda x: x['id'], reverse=True)


        return {'search_results': res}


    def new_reception_name(self, now):
        today = datetime.strftime(now, '%Y-%m-%d')
        query = "SELECT COUNT(id) AS id_count FROM stock_reception WHERE create_date AT TIME ZONE 'UTC' >= '%s'"%today
        self.env.cr.execute(query)
        res = self.env.cr.dictfetchall()
        if res:
            number = int(res[0]['id_count'])+1
        else:
            number = 1

        name = datetime.strftime(now, '%m-%d-%y') + '-' + str(number)
        return name


    def create_reception(self, data):
        """
            {'purchase_orders': [
                {'name': 'DD76004', 'id': 5, 'vendor_internalid': 140762},
                {'name': 'DD76474', 'id': 13},
                {'name': 'DD76610', 'id': 16}
                ],
             'add_method': 'vendor',
             'selected_vendor': {
                 'id': 1234,
                 'internalid': '1904',
                 'name': 'Fortress Railing Products, LLC',
                 'status': {'isTrusted': True}
                 }
             }
        """
        now = datetime.utcnow()

        if data.get('selected_vendor'):
            vendor_id = data['selected_vendor']['id']
        else:
            vendor_obj = self.env['stock.vendor']

        purchases = [(4,purchase['id']) for purchase in data['purchase_orders']]

        vals = {
            'name': self.new_reception_name(now),
            'purchase_orders': purchases,
            'date': now,
            'status': 'Open',
            'lp_count': 0,
        }

        reception = self.env['stock.reception'].create(vals)
        return {'new_record': reception.id}


    def get_reception(self, reception_id):
        reception_obj = self.env['stock.reception']
        reception = reception_obj.browse(int(reception_id))

        purchase_orders = [
            {'name': purchase.name,
             'receive_by': datetime.strftime(purchase.receive_by, '%m-%d-%y') if purchase.receive_by else None,
             'date': datetime.strftime(purchase.date, '%m-%d-%y'),
             'internalid': purchase.internalid,
             'id': purchase.id} for purchase in reception.purchase_orders
        ]

        vals = {
            'name': reception.name,
            'lp_count': reception.lp_count,
            'purchase_orders': purchase_orders,
            'date': datetime.strftime(reception.date, '%m-%d-%y'),
            'status': reception.status,
            'purchase_summary': [],
            'license_plates': [],
        }

        purchase_summary = self.get_purchase_orders_reception_summary(reception.purchase_orders)
        license_plates = {}
        #For each product in the saved receiving document
        for reception_line in reception.products:
            if reception_line.license_plate:
                lp = reception_line.license_plate
                if not license_plates.get(lp.id):
                    vals['license_plates'].append({
                        'id': lp.id,
                        'name': lp.name,
                        'status': lp.status
                    })

                    license_plates[lp.id] = lp.id

            product_internalid = reception_line.product_internalid
            purchase_internalid = reception_line.purchase_internalid

            #If the product on the reception is in the purchase order summary
            if purchase_summary.get(product_internalid):
                #Add the specific PO/LP qty to the summary total
                purchase_summary[product_internalid]['qty_received'] += reception_line.qty
                purchase_summary[product_internalid]['qty_remaining'] -= reception_line.qty

                for po_line_data in purchase_summary[product_internalid]['purchase_lines']:
                   #Add the same qty to the PO specific level
                   if po_line_data['purchase_internalid'] == purchase_internalid:
                        po_line_data['qty_received'] += reception_line.qty
                        po_line_data['qty_remaining'] -= reception_line.qty

                        #Add the same qty to the specific license plate that the reception line is assigned to
                        po_line_data['lp_lines'].append({
                            'lp_name': reception_line.license_plate.name,
                            'lp_id': reception_line.license_plate.id,
                            'qty_received': reception_line.qty
                        })

      #  all_received = False
       # if reception.status != 'Received':
      #      for product_id, product_vals in purchase_summary.items():
     #           if product_vals['qty_received'] != product_vals['qty_remaining_unreceived']:
    #                all_received = False
   #                 break

#            if all_received:
 #               reception.status = 'Received'
  #              vals['status'] = 'Received'
            else:
                #If an item is removed from a PO, but for some reason has already been added to a receipt,
                #It can't be shown because the view depends on elements from the PO.
                #this means it is stuck and can't be removed. And yes, this is a valid scenario because it has happened
                #Checking if the receipt is received is imperative because once goods are received
                #The PO lines are removed and would cause this to be triggered in error
                if reception.status != 'Received':
                    reception_line.unlink()
        data = []
        for product_id, product_vals in purchase_summary.items():
            if reception.status != 'Received':
                product_vals['product_internalid'] = product_id
                if product_vals['qty_received'] == product_vals['qty_remaining_unreceived']:
                    product_vals['color'] = 'lightgreen'
                    product_vals['color_position'] = '3'
                elif product_vals['qty_received'] > product_vals['qty_remaining_unreceived']:
                    product_vals['color'] = '#949391'
                    product_vals['color_position'] = '0'
                elif product_vals['qty_received'] < product_vals['qty_remaining_unreceived'] and product_vals['qty_received'] > 0:
                    product_vals['color'] = 'orange'
                    product_vals['color_position'] = '2'
                else:
                    product_vals['color'] = '#F37155'
                    product_vals['color_position'] = '1'
            else:
                product_vals['color'] = 'white'
                product_vals['color_position'] = '1'

            for line in product_vals['purchase_lines']:
                if line['qty_received'] == line['qty_remaining_unreceived']:
                    line['color'] = 'lightgreen'
                    line['color_position'] = '3'
                elif line['qty_received'] > line['qty_remaining_unreceived']:
                    line['color'] = '#949391'
                    line['color_position'] = '0'
                elif line['qty_received'] < line['qty_remaining_unreceived'] and line['qty_received'] > 0:
                    line['color'] = 'orange'
                    line['color_position'] = '2'
                else:
                    line['color'] = '#F37155'
                    line['color_position'] = '1'

            data.append(product_vals)

        vals['purchase_summary'] = data
        return vals


    def save_reception_progress(self, reception_id, reception_data):
        #{'changed': True,
         #'color': 'orange',
         #'ddn': '29519-A',
         #'filter_size': 'l',
         #'filter_weight': 'l',
         #'mpn': 'CB010612E2G56',
         #'options': 'Finish: Trex - Coastal Bluff\n'
         #   'Size: 1x5 1/2\n'
         #   'Length: 12 ft\n'
         #   'Option: Grooved',
         #'product_image': 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg',
         #'product_internalid': '43088',
         #'product_name': 'Trex Enhance Natural Decking',
         #'purchase_description': 'Trex Enhance Natural Decking',
         #'purchase_lines': [{'lp_lines': [],
         #    'purchase_internalid': '14343088',
         #    'purchase_name': 'DD78011',
         #    'vendor_name': 'vendor name',
         #    'qty_received': 25,
         #    'qty_remaining': 168}],
         #'qty_received': 25,
         #'qty_remaining': 143,
         #'receive_qty': '25',
         #'sku': 'CB010612E2G56',
         #'upc': '652835289169'}

        lp_obj = self.env['license.plate']
        bin_obj = self.env['bin']

        license_plate = reception_data['license_plate'].strip()
        bin = reception_data['receiving_bin'].strip()
        header_lps = lp_obj.search([('name', 'ilike', license_plate)])
        bins = bin_obj.search([('name', 'ilike', bin)])
        if not header_lps:
            return {'success': False, 'error_message': 'LP Not Found. Please reset LP'}

        header_lp = header_lps[0]
        if header_lp.reception and str(header_lp.reception.id) != str(reception_id):
            return {'success': False, 'error_message': 'LP tied to another reception. Please reset LP'}
        header_lp.reception = reception_id
        header_lp.bin = bins[0].id
        #For each line in the purchase grouped summary
        for reception_group_line in reception_data['purchase_summary']:
            #We only want to work with lines that have been changed
            if reception_group_line.get('changed'):
                #For each PO Line within the summary line
                header_lp_used = False
                for po_line in reception_group_line['purchase_lines']:
                    if po_line['qty_received'] > 0:
                        po_line_qty_total = po_line['qty_received']
                        total_lp_received_qty = 0
                        #If the PO line has existing license plates
                        if len(po_line['lp_lines']) > 0:
                            #For each LP Line
                            for lp_line in po_line['lp_lines']:
                                lp_line_qty = lp_line['qty_received']
                                lp_id = lp_line['lp_id']
                                lp_name = lp_line['lp_name']
                                if lp_name == header_lp.name:
                                    header_lp_used = True

                                total_lp_received_qty += lp_line_qty
                                #The LP line is either zero or not
                                if lp_line_qty == 0:
                                    _logger.info('Deleting reception line with LP: %s'%lp_line['lp_name'])
                                    self.delete_reception_line(reception_id, reception_group_line, \
                                        po_line, lp_id
                                    )

                                #If an existing LP Line has been modified
                                elif lp_line.get('changed'):
                                    self.upsert_reception_line(reception_id, reception_group_line, po_line, \
                                       header_lp.id, lp_line['qty_received'], 'replace'
                                    )

                            remainder = po_line['qty_received'] - total_lp_received_qty
                            if remainder != 0 and header_lp_used:
                                raise

                            if not header_lp_used:
                                self.upsert_reception_line(reception_id, reception_group_line, po_line, \
                                    header_lp.id, remainder, 'replace'
                                )

                        #This is the first time this line is received and there are no LPs
                        else:
                            self.upsert_reception_line(reception_id, reception_group_line, po_line, \
                                header_lp.id, po_line['qty_received'], 'replace'
                            )

                    else:
                        self.delete_reception_line(reception_id, reception_group_line, po_line, False)

        return {'success': True, 'reception': self.get_reception(reception_id)}


    def upsert_reception_line(self, reception_id, reception_group_line, po_line, lp_id, qty, operation):
        product_internalid = reception_group_line['product_internalid']
        options = reception_group_line['options']
        purchase_internalid = po_line['purchase_internalid']
        product_id = reception_group_line['product_id']
        reception_line_obj = self.env['stock.reception.line']
        reception_lines = reception_line_obj.search([
            ('reception', '=', int(reception_id)),
            ('product_internalid', '=', str(product_internalid)),
            ('purchase_internalid', '=', str(purchase_internalid)),
            ('license_plate', '=', int(lp_id)),
        ])

        if reception_lines:
            reception_line = reception_lines[0]
            if operation == 'replace':
                reception_line.qty = qty
            elif operation == 'update':
                reception_line.qty += float(qty)
            else:
                raise

            _logger.info('Updated Reception Line: %s'%reception_line.id)

        else:
            vals = {
                'reception': int(reception_id),
                'product_internalid': str(product_internalid),
                'product': int(product_id),
                'qty': qty,
                'options': options,
                'license_plate': int(lp_id),
                'purchase_internalid': purchase_internalid,
                'purchase_name': po_line['purchase_name'],
                'vendor_name': po_line['vendor_name'],
            }

            reception_line = reception_line_obj.create(vals)
            _logger.info('Created Reception Line: %s'%reception_line.id)
        return True


    def delete_reception_line(self, reception_id, reception_group_line, po_line, lp_id):
        product_internalid = reception_group_line['product_internalid']
        purchase_internalid = po_line['purchase_internalid']

        query = "DELETE FROM stock_reception_line WHERE reception = '%s' AND product_internalid = '%s'" \
            "\nAND purchase_internalid = '%s'" % (reception_id, product_internalid, purchase_internalid)

        if lp_id:
            query += "\nAND license_plate = '%s'"%lp_id

        self.env.cr.execute(query)
        return True
