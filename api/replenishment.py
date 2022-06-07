from odoo import api, fields, models, SUPERUSER_ID, _
from datetime import datetime
import logging
import json
_logger = logging.getLogger(__name__)
from pprint import pprint as pp


class StockWms(models.TransientModel):
    _inherit = 'stock.wms'

    def get_replen_data(self, replen_type):
        if replen_type == 'demand':
            return self.get_demand_replen_data()

        if replen_type == 'minmax':
            return self.get_minmax_replen_data()

        return {'error': 'replen_type_not_supported'}


    def get_replen(self, replen_id):
        replen_obj = self.env['stock.replenishment']
        replen = replen_obj.browse(int(replen_id))
        res = {
            'id': replen.id,
            'name': replen.name,
            'date': replen.create_date,
            'replen_type': replen.replen_type,
            'status': replen.status,
            'user_id': replen.create_uid.id,
            'user_name': replen.create_uid.partner_id.name
        }

        products = self.get_replen_lines(replen.lines)
        res['lines'] = products

        return res


    def get_replen_lines(self, replen_lines):
        product_internalids = []

        for line in replen_lines:
            #Goal is to get inventory only for lines that have not been processed
            if line.status == 'open' and line.product.internalid and line.product.internalid not in product_internalids:
                product_internalids.append(line.product.internalid)

        product_inventory = []
        if product_internalids:
            product_inventory = self.get_multi_product_inventory(product_internalids)
            product_inventory = product_inventory['data']

        return_lines = []

        for line in replen_lines:
            img_path = line.product.img_path
            img_no_selection = 'https://www.decksdirect.com/media/catalog/product/placeholder/default/image-coming-soon_1.jpg'
            if img_path == 'https://www.decksdirect.com/media/catalog/productno_selection' or not img_path:
                img_path = img_no_selection

            line_vals = {
                'concat_id': str(line.product.id) + '_' + str(line.to_bin.id),
                'product_id': line.product.id,
                'product_internalid': line.product.internalid,
                'product_image': img_path,
                'sku': line.product.sku,
                'ddn': line.product.ddn,
                'mpn': line.product.mpn,
                'upc': line.product.upc,
                'to_bin_id': line.to_bin.id,
                'to_bin_name': line.to_bin.name,
                'to_bin_internalid': line.to_bin.internalid,
                'to_bin_min': line.product.bin_min,
                'to_bin_max': line.product.bin_max,
                'replen_line_id': line.id,
                'cancel_picked_remainder': line.cancel_picked_remainder,
                'replen_id': line.replen.id,
                'available_pick_bins': [],
                'putaway_lines': []
            }

            for putaway_line in line.putaway_lines:
                line_vals['putaway_lines'].append(self.putaway_line_vals(putaway_line))

            product_internalid = str(line.product.internalid)

            product_data = False
            if product_inventory:
                product_data = product_inventory.get(product_internalid)

            if product_data:
                bin_inventory = product_data['bin_inventory']
                for bin in bin_inventory:
                    if str(bin['internalid']) == str(line.to_bin.internalid):
                        line_vals['to_bin_available'] = bin['qty_available']
                        line_vals['to_bin_onhand'] = bin['qty_onhand']

                    if bin['bin_type'] in ['Overstock', 'Receiving']:
                        line_vals['available_pick_bins'].append(bin)

            self.calc_replen_line_fields(line, line_vals)
            return_lines.append(line_vals)

        return return_lines


    def new_replen_name(self, now):
        today = datetime.strftime(now, '%Y-%m-%d')
        query = "SELECT COUNT(id) AS id_count FROM stock_replenishment WHERE create_date AT TIME ZONE 'UTC' >= '%s'"%today
        self.env.cr.execute(query)
        res = self.env.cr.dictfetchall()
        if res:
            number = int(res[0]['id_count'])+1
        else:
            number = 1

        name = datetime.strftime(now, '%m-%d-%y') + '-' + str(number)
        return name


    def create_replen(self, data):
        """{'bins': [{'id': '33364_145762',
                   'pick_bin': {'ddn': '68255-A',
                                'internalid': '33364',
                                'mpn': '3040BK2',
                                'ninety_days_daily_average': '12.37',
                                'ninety_days_sold': 1113,
                                'overstock_available': 870,
                                'overstock_bins': [{'available': 870,
                                                    'bin_internalid': '120835',
                                                    'bin_max': '480',
                                                    'bin_min': '60',
                                                    'bin_name': '40R017',
                                                    'bin_type': 'Overstock',
                                                    'onhand': 870}],
                                'overstock_onhand': 870,
                                'pick_bin_internalid': '145762',
                                'pick_bin_name': '100C030',
                                'product_id': 338184,
                                'product_internalid': '33364',
                                'qty_to_replen': 443,
                                'sixty_days_daily_average': '9.47',
                                'sixty_days_sold': 568,
                                'sku': '3040BK2',
                                'thirty_days_daily_average': '12.57',
                                'thirty_days_sold': 377},
                   'status': True},
         'replen_method': 'minmax'}"""

        replen_obj = self.env['stock.replenishment']

        now = datetime.utcnow()
        name = self.new_replen_name(now)
        replen_type = data['replen_method']

        vals = {
            'name': name,
            'status': 'open',
            'replen_type': replen_type
        }

        vals['lines'] = self.create_replen_lines(replen_type, data['bins'])
        replen = replen_obj.create(vals)

        return {'new_record': replen.id}


    def create_replen_lines(self, replen_type, bins):
        #demand
        """{'bins': [{'id': 'undefined_undefined',
                   'pick_bin': {'ddn': '70777-A',
                                'mpn': 'K048-005',
                                'pick_bin_id': 137332,
                                'pick_bin_name': '210B166',
                                'preferred_bin': 137332,
                                'product': 329302,
                                'product_id': 329302,
                                'qty_available': 80,
                                'qty_demand': 138,
                                'qty_overstock': 0,
                                'qty_receiving': 0,
                                'shipping_type': 'Parcel',
                                'short_qty': 58,
                                'sku': 'K048-005',
                                'stock_type': 'Crossdock'},
                   'status': True}],
         'replen_method': 'demand'}"""

        #minmax
        """'pick_bin': {'ddn': '88712-A',
                    'internalid': '16794',
                    'mpn': 'RSL405-G3',
                    'ninety_days_daily_average': '1.71',
                    'ninety_days_sold': 154,
                    'overstock_available': 101,
                    'overstock_bins': [{'available': 101,
                                        'bin_internalid': '122034',
                                        'bin_max': '50',
                                        'bin_min': '10',
                                        'bin_name': '80R013',
                                        'bin_type': 'Overstock',
                                        'onhand': 101}],
                    'overstock_onhand': 101,
                    'pick_bin_internalid': '114687',
                    'pick_bin_name': '130B213',
                    'product_id': 336323,
                    'product_internalid': '16794',
                    'qty_to_replen': 42,
                    'sixty_days_daily_average': '1.95',
                    'sixty_days_sold': 117,
                    'sku': 'RSL405-G3',
                    'thirty_days_daily_average': '2.80',
                    'thirty_days_sold': 84}"""

        lines = []
        bin_obj = self.env['bin']
        product_obj = self.env['product']

        for pick_bin in bins:
            pick_bin = pick_bin['pick_bin']

            if replen_type == 'minmax':
                bin = bin_obj.get_or_create_bin(pick_bin['pick_bin_name'], pick_bin['pick_bin_internalid'])
                bin_id = bin.id
                qty_to_replen = pick_bin['qty_to_replen']

            elif replen_type == 'demand':
                bin_id = pick_bin['pick_bin_id']
                bin = bin_obj.browse(int(bin_id))
                product = product_obj.browse(int(pick_bin['product_id']))

                if pick_bin['stock_type'] == 'Stock':
                    min = product.bin_min or 0
                    max = product.bin_max or 0
                    available = int(pick_bin['qty_available'])
                    qty_to_replen = max - available
                else:
                    qty_to_replen = pick_bin['short_qty']

            vals = {
                'product': pick_bin['product_id'],
                'to_bin': bin_id,
                'status': 'open',
                'qty_to_replen': qty_to_replen,
            }

            lines.append((0, 0, vals))
        return lines


    def get_demand_replen_data(self):
        data = self.get_demand_replen_grouping()
        if not data:
            return {'pick_bins': []}

        res = []

        if data.get('express'):
            if data['express'].get('Crossdock'):
                res.extend(self.explode_demand_grouping('Express', data['express']['Crossdock']))
            if data['express'].get('Stock'):
                res.extend(self.explode_demand_grouping('Express', data['express']['Stock']))

        if data.get('parcel'):
            if data['parcel'].get('Crossdock'):
                res.extend(self.explode_demand_grouping('Parcel', data['parcel']['Crossdock']))
            if data['parcel'].get('Stock'):
                res.extend(self.explode_demand_grouping('Parcel', data['parcel']['Stock']))

        return {'pick_bins': res}


    def explode_demand_grouping(self, shipping_type, data):
        product_obj = self.env['product']
        bin_obj = self.env['bin']
        #TODO: Fixme
        crossdock_bins = bin_obj.search([('name', '=', 'CrossDock')])
        if not crossdock_bins:
            raise

        crossdock_bin = crossdock_bins[0]

        res = []

        for product_id, vals in data.items():
            product = product_obj.browse(int(product_id))
            if not vals.get('preferred_bin'):
                bin = crossdock_bin
            else:
                bin = bin_obj.browse(int(vals['preferred_bin']))

            vals.update({
                'short_qty': int(vals['qty_demand']) - int(vals['qty_available']),
                'pick_bin_id': bin.id,
                'pick_bin_name': bin.name,
                'product_id': product.id,
                'sku': product.sku,
                'ddn': product.ddn,
                'mpn': product.mpn,
                'shipping_type': shipping_type
            })
            res.append(vals)

        return res


    def get_demand_replen_grouping(self):
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        conn = netsuite_obj.connection(netsuite)
        sale_vals = {
            'search_id': 3429,
            'record_type': 'transaction',
        }

        sale_product_response = None
        try:
       #     _logger.info('Downloading Netsuite Search Data')
            sale_product_response = conn.saved(sale_vals)

        except Exception as e:
            subject = 'Could not get all fulfillment data from Netsuite'
            self.env['integrator.logger'].submit_event('Netsuite', subject, str(e), False, 'admin')

   #     if not response or not response.get('data'):
    #        return True

        #{'id': None,
        #  'recordtype': None,
        #   'columns': {'item': {'name': 'K048-005-azk_pvr-wwhl-4x8rp-16x16g', 'internalid': '16362'}, 'formulanumeric': 308, 'formulatext': 'Stock'}}
        internalids = []

        if not sale_product_response or not sale_product_response.get('data'):
            print('Do Something')

        for each in sale_product_response['data']:
            row = each['columns']
            product_internalid = row['item']['internalid']
            if product_internalid not in internalids:
                internalids.append(product_internalid)

        if not internalids:
            print('Do Something 2')

        #  '9583': {'bin_inventory': [{'bin': 'W-T24',
        #                              'bin_type': '',
        #                              'bin_type_internalid': '',
        #                              'internalid': '112424',
        #                              'location_internalid': '2',
        #                              'location_name': 'Indianapolis FC',
        #                              'preferred': True,
        #                              'qty_available': 30,
        #                              'qty_onhand': 30,
        #                              'status': '1'}],
        #           'item_id': '9583',
        #           'location_internalid': '2',
        #           'location_name': 'Indianapolis FC',
        #           'qty_available': 30,
        #           'qty_onhand': 30}},
        product_data = self.get_multi_product_inventory(internalids)
        if not product_data:
            raise

        product_data = product_data['data']

        product_obj = self.env['product']
        bin_obj = self.env['bin']

        replen_data = {
            'parcel': {
                'Crossdock': {},
                'Stock': {}
             },
            'express': {
                'Crossdock': {},
                'Stock': {}
            }
        }

        for each in sale_product_response['data']:
            row = each['columns']
            product_internalid = row['item']['internalid']
            sku = None
            product_id = product_obj.find_netsuite_integrator_product(product_internalid, sku)
            qty_unfilled = row['formulanumeric']
            stock_type = row['formulatext']

            shipping_type = 'parcel'
            shipping_method = False
            shipmethod = each.get('shipmethod')
            if shipmethod:
                shipmethod_id = shipmethod['internalid']
                shipping_obj = self.env['shipping.method']
                shipping_methods = shipping_obj.search([('internalid', '=', shipmethod_id)])
                if shipping_methods:
                    shipping_method = shipping_methods[0]
                    if shipping_method.shipping_type == 'express':
                        shipping_type = 'express'

            if replen_data[shipping_type][stock_type].get(product_id):
                replen_data[shipping_type][stock_type][product_id]['qty_demand'] += qty_unfilled
                continue

            qty_preferred = 0
            qty_receiving = 0
            qty_overstock = 0
            qty_available = 0
            preferred_bin = None

            product_inventory = product_data.get(product_internalid)
            if not product_inventory:
                continue
                pp(each)
                print('Oops')
                raise

            skip_product = False
            for bin in product_inventory['bin_inventory']:
                bin_name = bin.get('bin')
                bin_internalid = bin.get('internalid')
                bin_available = bin.get('qty_available')

                if bin.get('preferred'):
                    qty_preferred += bin_available

                    if qty_preferred >= qty_unfilled:
                        skip_product = True
                        break

                    preferred_bin = bin_obj.get_or_create_bin(bin_name, bin_internalid)

                elif bin.get('bin_type') == 'Receiving':
                    qty_receiving += bin_available

                else:
                    qty_overstock += bin_available

            if skip_product:
                continue

            vals = {
                'product': product_id,
                'preferred_bin': preferred_bin.id if preferred_bin else None,
                'stock_type': stock_type,
                'qty_available': qty_preferred,
                'qty_demand': qty_unfilled,
                'qty_overstock': qty_overstock,
                'qty_receiving': qty_receiving
            }

            replen_data[shipping_type][stock_type][product_id] = vals

        return replen_data


    def get_minmax_replen_data(self):
        """{'data': {'11314': {'bins': [{'available': 53,
                                      'bin_internalid': '122463',
                                      'bin_max': '75',
                                      'bin_min': '8',
                                      'bin_name': '90S129',
                                      'bin_type': 'Overstock',
                                      'onhand': 53},
                                     {'available': 4,
                                      'bin_internalid': '142990',
                                      'bin_max': '75',
                                      'bin_min': '8',
                                      'bin_name': '90B060',
                                      'bin_type': 'Picking',
                                      'onhand': 4}],
                            'ddn': '20244-A',
                            'internalid': '11314',
                            'ninety_day_sold': 0,
                            'sixty_day_sold': 0,
                            'sixty_days_daily_average': 0.05555555555555555,
                            'sixty_days_sold': 5,
                            'thirty_day_sold': 0},
         'result': 'success'}"""
        product_obj = self.env['product']
        netsuite_obj = self.env['netsuite.integrator']
        setup_obj = self.env['netsuite.setup']
        netsuite_id = netsuite_obj.get_instance_id()
        netsuite = setup_obj.browse(netsuite_id)
        #TODO: Convert 1.0 to 2.0 so all can share the same url
        url = 'https://1243222.restlets.api.netsuite.com/app/site/hosting/restlet.nl?script=1353&deploy=1'
        conn = netsuite_obj.connection(netsuite, url_override=url)
        vals = {'give_dater': True}
        netsuite_data = json.loads(conn.request(vals))

        res = []
        product_data = netsuite_data['data']
        for product_internalid, product_vals in product_data.items():
            sku = None
            product_id = product_obj.find_netsuite_integrator_product(product_internalid, sku)
            product = product_obj.browse(product_id)
            product_bins = product_vals['bins']

            product_vals.update({
                'product_id': product_id,
                'product_internalid': product_internalid,
                'sku': product.sku,
                'ddn': product.ddn,
                'mpn': product.mpn
            })

            picking_bins = []
            overstock_bins = []

            overstock_onhand = 0
            overstock_available = 0
            #Preliminary check
            for bin in product_bins:
                if bin['bin_type'] == 'Overstock':
                    overstock_onhand += int(bin['onhand'])
                    overstock_available += int(bin['available'])
                    overstock_bins.append(bin)

                elif bin['bin_type'] == 'Picking':
                    picking_bins.append(bin)

            #We replen from overstock and if there are none, we will skip
            if not overstock_bins:
                continue

            for pick_bin in picking_bins:
                #Copy the product as each picking bin is a line to replenish
                vals = dict(product_vals)
                del vals['bins']

                qty_onhand = int(pick_bin['onhand'])
                qty_available = int(pick_bin['available'])
                min = int(pick_bin['bin_min'])
                max = int(pick_bin['bin_max'])
                #TODO: Replen available or onhand?

                if qty_onhand > min:
                    continue

                qty_needed = max - qty_onhand

                bin_internalid = pick_bin['bin_internalid']
                bin_name = pick_bin['bin_name']
                vals.update({
                    'pick_bin_name': bin_name,
                    'pick_bin_internalid': bin_internalid,
                    'qty_to_replen': qty_needed,
                    'overstock_onhand': overstock_onhand,
                    'overstock_available': overstock_available,
                    'overstock_bins': overstock_bins
                })

                res.append(vals)

        return {'pick_bins': res}


    def force_replen_complete(self, replen_id, force_vals):
        _logger.info('Force Complete')
        lp = self.env['license.plate'].browse(lp_id)
        for product in lp.products:
            product.qty_putaway = product.qty
        lp.status = 'Putaway'
        return {'result': 'success', 'license_plate': {'status': 'Putaway'}}


    def force_replen_line_complete(self, lp_id, force_vals):
        _logger.info('Force Complete')
        lp = self.env['license.plate'].browse(lp_id)
        for product in lp.products:
            product.qty_putaway = product.qty
        lp.status = 'Putaway'
        return {'result': 'success', 'license_plate': {'status': 'Putaway'}}


    def submit_replen_pick(self, replen_id, data):
        replen_obj = self.env['stock.replenishment']
        bin_obj = self.env['bin']
        line_obj = self.env['stock.replenishment.line']
        putaway_obj = self.env['stock.replenishment.line.putaway']

        replen_line_data = data['replen_line']
        qty_picked = data['qty_picked']
        replen_line_id = int(replen_line_data['replen_line_id'])

        if data.get('cancel_remainder'):
            replen_line = line_obj.browse(replen_line_id)
            if replen_line.status == 'open':
                replen_line.status = 'picked'

            replen_line_data = self.calc_replen_line_fields(replen_line, replen_line_data)
            return {'result': 'success', 'replen_line': replen_line_data}

        if not data.get('pick_bin'):
            replen_line = line_obj.browse(replen_line_id)
            replen_line_data = self.calc_replen_line_fields(replen_line, replen_line_data)
            return {'result': 'success', 'replen_line': replen_line_data}

        pick_bin = data['pick_bin']
        bin = bin_obj.get_or_create_bin(pick_bin['bin'], pick_bin['internalid'])

        vals = {
            'plan_line': replen_line_id,
            'pick_bin': bin.id,
            'qty_transferred': qty_picked
        }

        putaway_line = putaway_obj.create(vals)

        replen_line_data['putaway_lines'].append(self.putaway_line_vals(putaway_line))

        replen_line = line_obj.browse(replen_line_id)
        replen_line_data = self.calc_replen_line_fields(replen_line, replen_line_data)

        return {'result': 'success', 'replen_line': replen_line_data}


    def putaway_line_vals(self, putaway_line):
        vals = {
            'putway_line_id': putaway_line.id,
            'qty_transferred': putaway_line.qty_transferred,
            'bin_transfer_internalid': putaway_line.bin_transfer_internalid,
            'bin_transfer_name': putaway_line.bin_transfer_name,
            'pick_bin_id': putaway_line.pick_bin.id,
            'pick_bin_name': putaway_line.pick_bin.name,
            'pick_bin_internalid': putaway_line.pick_bin.internalid
        }

        return vals


    def calc_replen_line_fields(self, replen_line, replen_line_data):
        qty_picked = 0
        qty_putaway = 0
        qty_to_replen = replen_line.qty_to_replen
        qty_to_putaway = 0
        qty_available_to_move = 0

        putaway_inv = {}

        for putaway_line in replen_line.putaway_lines:
            transferred_qty = putaway_line.qty_transferred
            putaway_inv[putaway_line.pick_bin.internalid] = transferred_qty

            if putaway_line.bin_transfer_internalid:
                qty_putaway += transferred_qty
            else:
                qty_picked += transferred_qty

            qty_to_replen -= transferred_qty

        if replen_line.status == 'open':
            if qty_picked == replen_line.qty_to_replen:
                replen_line.status = 'picked'

        if replen_line.status == 'picked':
            if qty_picked == qty_putaway:
                replen_line.status = 'done'

        replen_line_data['qty_picked'] = qty_picked
        replen_line_data['qty_putaway'] = qty_putaway
        replen_line_data['qty_to_replen'] = qty_to_replen
        replen_line_data['qty_to_putaway'] = qty_picked - qty_putaway

        for inv_bin in replen_line_data['available_pick_bins']:
            if putaway_inv.get(inv_bin['internalid']):
                inv_bin['qty_onhand'] -= putaway_inv.get(inv_bin['internalid'])
                inv_bin['qty_available'] -= putaway_inv.get(inv_bin['internalid'])

            qty_available_to_move += inv_bin['qty_available']

        #If the total quantity available to pick has been picked but still does not fill the qty
        #Auto close the line as no more can be picked

        if qty_available_to_move < replen_line_data['qty_to_replen'] and qty_available_to_move == 0:
            replen_line_data['cancel_picked_remainder'] = True

        if replen_line_data['cancel_picked_remainder']:
            replen_line_data['qty_to_replen'] = 0
            if not replen_line.cancel_picked_remainder:
                replen_line.cancel_picked_remainder = True
                if qty_picked == 0:
                    replen_line.status = 'cancel'
                else:
                    replen_line.status = 'picked'

        if replen_line.status == 'open' and qty_available_to_move == 0:
            if qty_picked > 0:
                replen_line.status = 'picked'
            else:
                replen_line.status = 'cancel'

        color = 'white'
        color_position = '0'

        if replen_line.status == 'open':
            color = '#F37155'
            color_position = '2'
        elif replen_line.status == 'picked':
            color = 'orange'
        elif replen_line.status == 'done':
            color = 'lightgreen'

        replen_line_data['status'] = replen_line.status
        replen_line_data['color'] = color
        replen_line_data['color_position'] = color_position
        return replen_line_data


    def submit_replen_putaway(self, replen_id, data):
        _logger.info('Submitting Replen Line Putaway')

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

        bin_obj = self.env['bin']
        line_obj = self.env['stock.replenishment.line']

        replen_line_data = data['replen_line']
        replen_line = line_obj.browse(int(replen_line_data['replen_line_id']))

        qty_putaway = data['qty_putaway']

        product = replen_line.product

        transfer_vals = {
            'to_bin': {
                'id': replen_line_data['to_bin_id'],
                'internalid': replen_line_data['to_bin_internalid'],
                'name': replen_line_data['to_bin_name']
            },
            'memo': 'Bin Replenishment',
            'update_preferred_bin': False,
            'product': {
                'internalid': product.internalid,
            },
            'qty': qty_putaway,
        }

        for putaway_line in replen_line.putaway_lines:
            putaway_bin = putaway_line.pick_bin

            if putaway_line.bin_transfer_internalid:
                continue

            line_transfer_vals = dict(transfer_vals)
            line_transfer_vals.update({
                'from_bin': {
                    'id': putaway_bin.id,
                    'internalid': putaway_bin.internalid,
                    'name': putaway_bin.name
                }
            })

            self.submit_bin_transfer(line_transfer_vals)
            putaway_line.bin_transfer_internalid = '12345'
            putaway_line.bin_transfer_name = '12345'

        replen_line.status = 'done'

        replen_line_data = self.calc_replen_line_fields(replen_line, replen_line_data)
        return {'result': 'success', 'replen_line': replen_line_data}


    def replen_search(self, search_term=False, limit=20):
        replen_obj = self.env['stock.replenishment']
        replen_ids = False
        replens = False
        res = []
        if search_term:
            replens = replen_obj.search([('name', 'ilike', search_term)], limit=limit)
            if not replens:
                query = "SELECT replen.id FROM stock_replenishment replen" \
                    "\nWHERE replen.name ilike '%"+search_term+"%s'"

                self.env.cr.execute(query)
                res = self.env.cr.dictfetchall()
                replen_ids = [r['id'] for r in res]

        else:
            query = "SELECT id FROM stock_replenishment"
            query += "\nORDER BY write_date DESC LIMIT %s"%limit
            self.env.cr.execute(query)
            res = self.env.cr.dictfetchall()
            replen_ids = [r['id'] for r in res]

        if replens or replen_ids:
            if replens:
                replen_ids = replens.mapped('id')

            query = "SELECT replen.id, replen.write_date, replen.replen_type," \
                "\npartner.name AS user_name, replen.name AS replen_name, replen.status, replen.create_date AT TIME ZONE 'UTC' AS date" \
                "\nFROM stock_replenishment replen" \
                "\nJOIN res_users users ON (replen.create_uid = users.id)" \
                "\nJOIN res_partner partner ON (partner.id = users.partner_id)"

            if len(replen_ids) > 1:
                query += "\nWHERE replen.id IN %s" % str(tuple(replen_ids))
            else:
                query += "\nWHERE replen.id = %s" % replen_ids[0]

            self.env.cr.execute(query)

            replen_results = self.env.cr.dictfetchall()
            res = []
            for each in replen_results:
                vals = {
                    'id': each['id'],
                    'write_date': each['write_date'],
                    'name': each['replen_name'],
                    'replen_type': each['replen_type'],
                    'date': each['date'].strftime('%m-%d-%Y'),
                    'status': each['status'],
                    'user': each['user_name']
                }
                res.append(vals)


            res = sorted(res, key=lambda x: x['id'], reverse=True)

        return {'search_results': res}


