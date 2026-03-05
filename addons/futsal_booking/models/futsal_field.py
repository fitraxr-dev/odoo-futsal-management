from odoo import fields, models


class FutsalField(models.Model):
    _name = 'futsal.field'
    _description = 'Futsal Field'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(
        string='Field Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Field Code',
        copy=False,
    )
    price_per_hour = fields.Float(
        string='Price per Hour (Rp)',
        required=True,
        digits=(12, 0),
        tracking=True,
    )
    status = fields.Selection(
        selection=[
            ('available', 'Available'),
            ('maintenance', 'Maintenance'),
        ],
        string='Status',
        default='available',
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Field code must be unique.'),
        ('price_positive', 'CHECK(price_per_hour > 0)', 'Price per hour must be greater than zero.'),
    ]
