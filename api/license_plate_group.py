from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def lp_group_search(self, search_term=False, limit=20):
        lp_group_obj = self.env['license.plate.group']
        res = []
        lp_groups = False
        lp_group_ids = False
        if search_term:
            lp_groups = lp_group_obj.search([('name', 'ilike', search_term)], limit=limit)
            if not lp_groups:
                query = "SELECT DISTINCT lp_group_rel.group_id AS id" \
                "\nFROM license_plate_group_rel lp_group_rel" \
                "\nJOIN license_plate lp ON (lp_group_rel.lp_id = lp.id)" \
                "\nWHERE lp.name ilike '%"+search_term+"%'"
                self.env.cr.execute(query)
                res = self.env.cr.dictfetchall()
                lp_group_ids = [r['id'] for r in res]
        else:
            query = "SELECT id FROM license_plate_group ORDER BY write_date DESC LIMIT %s"%20
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            lp_group_ids = [r['id'] for r in res]

        if lp_groups or lp_group_ids:
            if lp_groups:
                lp_group_ids = lp_groups.mapped('id')

            query = "SELECT lp_group.id, lp_group.name, lp_group.write_date, lp.name AS lp_name, lp.status, lp.id AS lp_id" \
                "\nFROM license_plate_group lp_group" \
                "\nJOIN license_plate_group_rel lp_group_rel ON (lp_group.id = lp_group_rel.group_id)" \
                "\nJOIN license_plate lp ON (lp_group_rel.lp_id = lp.id)" \

            if len(lp_group_ids) > 1:
                query += "\nWHERE lp_group.id IN %s" % str(tuple(lp_group_ids))
            else:
                query += "\nWHERE lp_group.id = %s" % lp_group_ids[0]

            self.env.cr.execute(query)
            lp_group_results = self.env.cr.dictfetchall()
            res_dict = {}
            res = []
            for each in lp_group_results:
                if res_dict.get(each['id']):
                    res_dict[each['id']]['license_plates'].append({
                        'name': each['lp_name'],
                        'id': each['lp_id'],
                        'status': each['status']
                    })
                else:
                    vals = {
                        'id': each['id'],
                        'write_date': each['write_date'],
                        'name': each['name'],
                        'license_plates': [{
                            'name': each['lp_name'],
                            'id': each['lp_id'],
                            'status': each['status']
                        }]
                    }
                    res_dict[each['id']] = vals

            for k, v in res_dict.items():
                res.append(v)

            res = sorted(res, key=lambda x: x['id'], reverse=True)

        return {'search_results': res}


    def new_lp_group_name(self, now):
        today = datetime.strftime(now, '%Y-%m-%d')
        query = "SELECT COUNT(id) AS id_count FROM license_plate_group WHERE create_date AT TIME ZONE 'UTC' >= '%s'"%today
        self.env.cr.execute(query)
        res = self.env.cr.dictfetchall()
        if res:
            number = int(res[0]['id_count'])+1
        else:
            number = 1

        name = datetime.strftime(now, '%m-%d-%y') + '-' + str(number)
        return name


    def create_license_plate_group(self, data):
        """
            {'license_plates': [
                {'name': '1006-881', 'id': 5},
                {'name': '1006-882', 'id': 13},
                {'name': '1006-884', 'id': 16}
                ],
            }
        """
        now = datetime.utcnow()

        lps = [(4,lp['id']) for lp in data['license_plates']]

        vals = {
            'name': self.new_lp_group_name(now),
            'license_plates': lps,
            'date': now,
        }

        lp_group = self.env['license.plate.group'].create(vals)
        return {'new_record': lp_group.id}


    def submit_group_bin_putaway(self, group_line, transfer_vals):
        """{'bin_inventory': [{'bin': 'EC5',
                              'bin_type': 'Receiving',
                              'bin_type_internalid': '3',
                              'internalid': '112596',
                              'location_internalid': '2',
                              'location_name': 'Indianapolis FC',
                              'preferred': False,
                              'qty_available': 10,
                              'qty_onhand': 10,
                              'status': '1'},
                             {'bin': '2G-54-02',
                              'bin_type': '',
                              'bin_type_internalid': '',
                              'internalid': '32325',
                              'location_internalid': '2',
                              'location_name': 'Indianapolis FC',
                              'preferred': True,
                              'qty_available': 10,
                              'qty_onhand': 10,
                              'status': '1'}],
           'color': '#F37155',
           'color_position': '2',
           'ddn': '81047-A',
           'mpn': '53234696',
           'options': 'Length: 6 ft\nHeight: 34 in\nFinish: Antique Bronze',
           'preferred_bin_id': '32325',
           'preferred_bin_name': '2G-54-02',
           'preferred_bin_onhand': 10,
           'product_image': 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg',
           'product_internalid': '1263',
           'product_name': 'FE26 Traditional Adjust-a-Rail Stair Railing Panel by '
                           'Fortress Iron',
           'qty_available': 10,
           'qty_onhand': 10,
           'qty_putaway': 0,
           'qty_received': 10,
           'qty_remaining': 10,
           'qty_underavailable': 0,
           'sku': '53234696',
           'transferred_qty': '10',
           'qty': '10',
           'upc': '844530005575',
           'to_bin': '112083',
           'selected_lps': [12345],
           'lp_lines': {1700: {'lp_id': 1700,
                               'lp_line_ids': [3789],
                               'qty_putaway': 0.0,
                               'qty_received': 12.0}},
           'update_preferred_bin': False}"""

        _logger.info('Submitting Group Line Putaway')
        for k, lp_line in group_line['lp_lines'].items():
            line_ids = lp_line['lp_line_ids']

            lp_obj = self.env['license.plate']
            lp_line_obj = self.env['stock.reception.line']
            lp_lines = lp_line_obj.browse(line_ids)

            transfer_qty = float(group_line['transferred_qty'])
            qty_committed = float(reception_line['qty_underavailable'])
            #transfer_qty += qty_committed

            for line in lp_lines:
                if transfer_qty == 0:
                    break
                line_qty_remaining = line.qty - line.qty_putaway
                if transfer_qty > line_qty_remaining:
                    line.qty_putaway += line_qty_remaining
                    transfer_qty -= line_qty_remaining
                elif line_qty_remaining >= transfer_qty:
                    line.qty_putaway += transfer_qty
                    transfer_qty = 0


            lp = lp_obj.browse(int(transfer_vals['lp_id']))
            lp_status = 'Putaway'
            for product in lp.products:
                if product.qty > product.qty_putaway:
                    lp_status = 'Ready for Putaway'
                    break

            lp.status = lp_status
            lp_vals = {'status': lp_status}

        """{'from_bin': {'id': 16649, 'internalid': '112083', 'name': '2C-36-01A'},
            'product': {
                'ddn': '71548-A',
               'internalid': '23279',
                'item': 'SR010616TG48-trex_deck_trns-sr-54x6-16ft-grv',
                'mpn': 'SR010616TG48',
                'preferred': True,
                'qty_available': '1068',
                'qty_onhand': '1068',
                'sku': 'SR010616TG48',
                'status': '1',
                'upc': '652835062458'
            },
            'qty': '1068',
            'to_bin': {'id': 85061, 'internalid': '113327', 'name': '2K-40-02A'}}"""
        self.submit_bin_transfer(transfer_vals)
        return {'result': 'success', 'license_plate': lp_vals}


    def get_license_plate_group_putaway_details(self, lp_group_id):
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)

        lp_group_obj = self.env['license.plate.group']
        lp_group = lp_group_obj.browse(int(lp_group_id))

        lp_ids = [lp.id for lp in lp_group.license_plates]
        query = "SELECT DISTINCT product_internalid FROM stock_reception_line"
        if len(lp_ids) > 1:
            query += "\nWHERE license_plate IN %s"%str(tuple(lp_ids))
        else:
            query += "\nWHERE license_plate = %s"%lp_ids[0]

        self.env.cr.execute(query)
        res = self.env.cr.dictfetchall()
        product_internalids = [each['product_internalid'] for each in res]

        conn = netsuite_obj.connection(netsuite, url_override=netsuite.mobile_url)
        vals = {
            'operation': 'get_multi_inventory',
            'product_ids': product_internalids,
        }

        netsuite_data = conn.request(vals)
        #{'result': {'17852': {
        #     'bin_inventory': [{
        #         'bin': '2D-34-01',
        #         'bin_type': '',
        #         'bin_type_internalid': '',
        #         'internalid': '30354',
        #         'location_internalid': '2',
        #         'location_name': 'Indianapolis FC',
        #         'qty_available': '101',
        #         'qty_onhand': '101',
        #         'status': '1'
        #     }],
        # 'item_id': '17852'}}}
        live_inventory = netsuite_data['data']

        lp_summary = {}
        lps = []
        for license_plate in lp_group.license_plates:
            lp_receiving_bin_internalid = str(license_plate.bin.internalid)
            lps.append({
                'id': license_plate.id,
                'name': license_plate.name,
                'date': license_plate.date,
                'receiving_bin': {
                    'internalid': lp_receiving_bin_internalid,
                    'id': license_plate.bin.id,
                    'name': license_plate.bin.name
                },
                'status': license_plate.status,
            })

            for lp_line in license_plate.products:
                product_internalid = lp_line.product_internalid
                product_inventory = live_inventory.get(product_internalid)
                preferred_bin_name = None
                preferred_bin_id = None
                preferred_bin_onhand = None
                receive_bin_onhand = 0
                receive_bin_available = 0

                if not product_inventory:
                    bin_inventory = []
                else:
                    bin_inventory = product_inventory['bin_inventory']
                    for bin in bin_inventory:
                        if str(bin['internalid']) == lp_receiving_bin_internalid and not bin['preferred']:
                            receive_bin_onhand = float(bin['qty_onhand'])
                            receive_bin_available = float(bin['qty_available'])
                        if bin['preferred']:
                            preferred_bin_name = bin['bin']
                            preferred_bin_id = bin['internalid']
                            preferred_bin_onhand = bin['qty_onhand']

                qty_remaining = lp_line.qty - lp_line.qty_putaway

                #If this item is in the summary items list
                if lp_summary.get(product_internalid):
                    lp_summary[product_internalid]['qty_remaining'] += qty_remaining
                    lp_summary[product_internalid]['qty_received'] += lp_line.qty
                    lp_summary[product_internalid]['qty_putaway'] += lp_line.qty_putaway

                    #If this summary item has the same item/lp combo
                    if license_plate.id in lp_summary[product_internalid]['lp_lines'].keys():
                        lp_summary[product_internalid]['lp_lines'][license_plate.id]['qty_received'] += lp_line.qty
                        lp_summary[product_internalid]['lp_lines'][license_plate.id]['qty_putaway'] += lp_line.qty_putaway
                        lp_summary[product_internalid]['lp_lines'][license_plate.id]['lp_line_ids'].append(lp_line.id)

                    else:
                        lp_summary[product_internalid]['lp_lines'][license_plate.id] = {
                            'qty_received': lp_line.qty,
                            'qty_putaway': lp_line.qty_putaway,
                            'lp_line_ids': [lp_line.id]
                        }

                else:
                    img_path = lp_line.product.img_path
                    img_no_selection = 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg'
                    if img_path == 'https://www.decksdirect.com/media/catalog/productno_selection' or not img_path:
                        img_path = img_no_selection

                    lp_summary[product_internalid] = {
                        'product_internalid': product_internalid,
                        'product_name': lp_line.product.purchase_description,
                        'product_image': img_path,
                        'preferred_bin_name': preferred_bin_name,
                        'preferred_bin_id': preferred_bin_id,
                        'preferred_bin_onhand': preferred_bin_onhand,
                        'mpn': lp_line.product.mpn,
                        'ddn': lp_line.product.ddn,
                        'upc': lp_line.product.upc,
                        'sku': lp_line.product.sku,
                        'bin_inventory': bin_inventory,
                        'options': lp_line.options,
                        'qty_received': lp_line.qty,
                        'qty_onhand': receive_bin_onhand,
                        'qty_available': receive_bin_available,
                        'qty_remaining': qty_remaining,
                        'qty_putaway': lp_line.qty_putaway,
                        'lp_lines': {
                            license_plate.id: {
                                'lp_id': license_plate.id,
                                'qty_received': lp_line.qty,
                                'qty_putaway': lp_line.qty_putaway,
                                'lp_line_ids': [lp_line.id]
                            }
                        }
                    }
        #Iterate over items again to convert to a list
        items_summary = []
        for product_internalid, line_val in lp_summary.items():
            qty_remaining = line_val['qty_remaining']
            qty_received = line_val['qty_received']

            receive_bin_available = line_val['qty_available']
            #If the available quantity is less than the remaining qty, we can't process it all
            #allow to process what is left
            qty_underavailable = 0
            if qty_remaining > receive_bin_available:
                qty_remaining = receive_bin_available
                qty_underavailable = qty_remaining - receive_bin_available

            color = 'white'
            color_position = '0'
            if qty_received == qty_remaining:
                color = '#F37155'
                color_position = '2'
            elif qty_remaining == 0:
                color = 'lightgreen'
            elif qty_remaining > 0:
                color = 'orange'
                color_position = '3'

            line_val['color'] = color
            line_val['color_position'] = color_position
            line_val['qty_remaining'] = qty_remaining
            line_val['qty_underavailable'] = qty_underavailable
            if qty_remaining > 0:
                line_val['show_force_complete'] = False

            lp_lines = []
            for lp_id, lp_vals in line_val['lp_lines'].items():
                lp_lines.append(lp_vals)

            line_val['lp_lines'] = lp_lines
            items_summary.append(line_val)

        lp_group_vals = {
            'name': lp_group.name,
            'date': lp_group.date,
            'license_plates': lps,
            'items_summary': items_summary
        }

        return lp_group_vals
