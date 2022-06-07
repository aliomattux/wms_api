{
    'name': 'WMS',
    'version': '1.1',
    'author': 'Kyle Waid',
    'category': 'Sales Management',
    'depends': ['integrator_netsuite', 'integrator_magento'],
    'website': 'https://www.gcotech.com',
    'description': """ 
    """,
    'data': [
        'security/ir.model.access.csv',
        'views/core.xml',
        'views/bin.xml',
        'views/license_plate.xml',
        'views/fulfillment.xml',
        'views/replenishment.xml',
        'views/purchase.xml',
        'report/license_plate_report_template.xml',
        'report/license_plate_report.xml',
        'report/bin_report_template.xml',
        'report/bin_report.xml',
        'wizard/no_preferred_bin.xml',
        'wizard/empty_pick_bins.xml'
    ],
    'test': [
    ],
    'installable': True,
    'auto_install': False,
}
