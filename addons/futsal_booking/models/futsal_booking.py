from datetime import datetime, time as dtime

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class FutsalBooking(models.Model):
    _name = 'futsal.booking'
    _description = 'Futsal Field Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'booking_date desc, start_time desc'

    # ------------------------------------------------------------------ #
    #  Fields                                                              #
    # ------------------------------------------------------------------ #

    name = fields.Char(
        string='Booking Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    customer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        tracking=True,
    )
    field_id = fields.Many2one(
        comodel_name='futsal.field',
        string='Field',
        required=True,
        tracking=True,
        domain=[('status', '=', 'available'), ('active', '=', True)],
    )
    booking_date = fields.Date(
        string='Booking Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    start_time = fields.Float(
        string='Start Time',
        required=True,
        help='24-hour format, e.g. 14.5 = 14:30',
    )
    end_time = fields.Float(
        string='End Time',
        required=True,
        help='24-hour format, e.g. 16.0 = 16:00',
    )
    duration = fields.Float(
        string='Duration (hours)',
        compute='_compute_duration',
        store=True,
    )
    price_unit = fields.Float(
        string='Price per Hour (Rp)',
        digits=(12, 0),
    )
    total_amount = fields.Float(
        string='Total Amount (Rp)',
        compute='_compute_total_amount',
        store=True,
        digits=(12, 0),
        tracking=True,
    )
    sales_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Sales Order',
        copy=False,
        readonly=True,
        tracking=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        copy=False,
        readonly=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    # Calendar datetime fields (computed from booking_date + start/end time)
    datetime_start = fields.Datetime(
        string='Start Datetime',
        compute='_compute_datetime_slots',
        store=True,
    )
    datetime_end = fields.Datetime(
        string='End Datetime',
        compute='_compute_datetime_slots',
        store=True,
    )

    # Smart-button counters
    so_count = fields.Integer(compute='_compute_so_count')
    invoice_count = fields.Integer(compute='_compute_invoice_count')

    # ------------------------------------------------------------------ #
    #  Onchange                                                            #
    # ------------------------------------------------------------------ #

    @api.onchange('field_id')
    def _onchange_field_id(self):
        if self.field_id:
            self.price_unit = self.field_id.price_per_hour

    # ------------------------------------------------------------------ #
    #  Computed                                                            #
    # ------------------------------------------------------------------ #

    @api.depends('booking_date', 'start_time', 'end_time')
    def _compute_datetime_slots(self):
        for rec in self:
            if rec.booking_date:
                def to_dt(t):
                    h = int(t)
                    m = int(round((t - h) * 60))
                    return datetime.combine(rec.booking_date, dtime(h, min(m, 59)))
                rec.datetime_start = to_dt(rec.start_time)
                rec.datetime_end = to_dt(rec.end_time)
            else:
                rec.datetime_start = False
                rec.datetime_end = False

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for rec in self:
            rec.duration = max(rec.end_time - rec.start_time, 0.0)

    @api.depends('duration', 'price_unit')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = rec.duration * rec.price_unit

    def _compute_so_count(self):
        for rec in self:
            rec.so_count = 1 if rec.sales_order_id else 0

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = 1 if rec.invoice_id else 0

    # ------------------------------------------------------------------ #
    #  Constraints                                                         #
    # ------------------------------------------------------------------ #

    @api.constrains('start_time', 'end_time')
    def _check_time_range(self):
        for rec in self:
            if rec.start_time < 0 or rec.end_time > 24:
                raise ValidationError(_('Time must be between 00:00 and 24:00.'))
            if rec.start_time >= rec.end_time:
                raise ValidationError(_('End time must be after start time.'))

    @api.constrains('field_id', 'booking_date', 'start_time', 'end_time', 'state')
    def _check_no_overlap(self):
        for rec in self:
            if rec.state == 'cancel':
                continue
            overlapping = self.search([
                ('id', '!=', rec.id),
                ('field_id', '=', rec.field_id.id),
                ('booking_date', '=', rec.booking_date),
                ('state', 'not in', ['cancel']),
                ('start_time', '<', rec.end_time),
                ('end_time', '>', rec.start_time),
            ])
            if overlapping:
                other = overlapping[0]
                raise ValidationError(_(
                    'Booking conflict! Field "%(field)s" on %(date)s is already booked '
                    'by %(customer)s from %(start)s to %(end)s (ref: %(ref)s).',
                    field=rec.field_id.name,
                    date=rec.booking_date,
                    customer=other.customer_id.name,
                    start=self._float_to_time(other.start_time),
                    end=self._float_to_time(other.end_time),
                    ref=other.name,
                ))

    # ------------------------------------------------------------------ #
    #  ORM overrides                                                       #
    # ------------------------------------------------------------------ #

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('futsal.booking') or _('New')
                )
        return super().create(vals_list)

    # ------------------------------------------------------------------ #
    #  Workflow actions                                                    #
    # ------------------------------------------------------------------ #

    def action_confirm(self):
        """Confirm booking and automatically create a linked Sale Order."""
        for rec in self:
            # Resolve product named "Sewa Lapangan" (service type)
            product = self.env['product.product'].search(
                [('name', '=', 'Sewa Lapangan'), ('type', '=', 'service')],
                limit=1,
            )
            if not product:
                raise UserError(_(
                    'Product "Sewa Lapangan" (service type) was not found. '
                    'Please create it before confirming a booking.'
                ))
            so = self.env['sale.order'].create({
                'partner_id': rec.customer_id.id,
                'origin': rec.name,
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'name': (
                        f'[{rec.field_id.name}] {rec.booking_date} '
                        f'{self._float_to_time(rec.start_time)}'
                        f'–{self._float_to_time(rec.end_time)}'
                    ),
                    'product_uom_qty': rec.duration,
                    'price_unit': rec.price_unit,
                })],
            })
            rec.sales_order_id = so
            rec.state = 'confirmed'
            rec.message_post(body=_('Booking confirmed. Sales Order %s created.', so.name))

    def action_start(self):
        for rec in self:
            rec.state = 'in_progress'

    def action_done(self):
        for rec in self:
            rec.state = 'done'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'

    # ------------------------------------------------------------------ #
    #  Smart-button actions                                                #
    # ------------------------------------------------------------------ #

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sales_order_id.id,
            'view_mode': 'form',
        }

    def action_create_invoice(self):
        """Create a customer invoice directly from this booking."""
        self.ensure_one()
        if self.invoice_id:
            raise UserError(_('An invoice already exists for this booking.'))
        # Prefer SO-based invoice if SO exists; otherwise create directly
        if self.sales_order_id:
            self.sales_order_id.action_confirm()
            invoice = self.sales_order_id._create_invoices()
            self.invoice_id = invoice[:1]
        else:
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.customer_id.id,
                'invoice_origin': self.name,
                'invoice_line_ids': [(0, 0, {
                    'name': (
                        f'[{self.field_id.name}] {self.booking_date} '
                        f'{self._float_to_time(self.start_time)}'
                        f'–{self._float_to_time(self.end_time)}'
                    ),
                    'quantity': self.duration,
                    'price_unit': self.price_unit,
                })],
            })
            self.invoice_id = invoice
        self.message_post(body=_('Invoice %s created.', self.invoice_id.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _float_to_time(value):
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        return f'{hours:02d}:{minutes:02d}'
