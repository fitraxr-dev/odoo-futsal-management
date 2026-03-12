{
    'name': 'Futsal Field Booking',
    'version': '19.0.1.0.0',
    'category': 'Services/Booking',
    'summary': 'Manage futsal field rentals, availability tracking, and bookings',
    'description': """
        Futsal Field Booking Management
        ================================
        Features:
        - Manage futsal fields with status: Available / Maintenance
        - Create and manage customer bookings
        - Track booking lifecycle: Draft → Confirmed → In Progress → Done
        - Automatic Sales Order generation on confirmation
        - Duration and total price auto-computation
        - Overlap validation per field and date
    """,
    'author': 'Fitra Rifki Firdaus',
    'depends': ['base', 'mail', 'sale', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/futsal_field_views.xml',
        'views/futsal_booking_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
