import io
from collections import OrderedDict
from decimal import Decimal

import pytz
from defusedcsv import csv
from django import forms
from django.db.models import DateTimeField, Max, OuterRef, Subquery, Sum
from django.dispatch import receiver
from django.utils.formats import localize
from django.utils.translation import ugettext as _, ugettext_lazy

from pretix.base.models import InvoiceAddress, Order, OrderPosition
from pretix.base.models.orders import OrderFee, OrderPayment, OrderRefund

from ..exporter import BaseExporter
from ..signals import register_data_exporters


class OrderListExporter(BaseExporter):
    identifier = 'orderlistcsv'
    verbose_name = ugettext_lazy('List of orders (CSV)')

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('paid_only',
                 forms.BooleanField(
                     label=_('Only paid orders'),
                     initial=True,
                     required=False
                 )),
            ]
        )

    def _get_all_tax_rates(self, qs):
        tax_rates = set(
            a for a
            in OrderFee.objects.filter(
                order__event=self.event
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates |= set(
            a for a
            in OrderPosition.objects.filter(
                order__event=self.event
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates = sorted(tax_rates)
        return tax_rates

    def render(self, form_data: dict):
        output = io.StringIO()
        tz = pytz.timezone(self.event.settings.timezone)
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        p_date = OrderPayment.objects.filter(
            order=OuterRef('pk'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()

        qs = self.event.orders.annotate(
            payment_date=Subquery(p_date, output_field=DateTimeField())
        ).select_related('invoice_address').prefetch_related('invoices')
        if form_data['paid_only']:
            qs = qs.filter(status=Order.STATUS_PAID)
        tax_rates = self._get_all_tax_rates(qs)

        headers = [
            _('Order code'), _('Order total'), _('Status'), _('Email'), _('Order date'),
            _('Company'), _('Name'), _('Address'), _('ZIP code'), _('City'), _('Country'), _('VAT ID'),
            _('Date of last payment'), _('Fees'), _('Order locale')
        ]

        for tr in tax_rates:
            headers += [
                _('Gross at {rate} % tax').format(rate=tr),
                _('Net at {rate} % tax').format(rate=tr),
                _('Tax value at {rate} % tax').format(rate=tr),
            ]

        headers.append(_('Invoice numbers'))

        writer.writerow(headers)

        full_fee_sum_cache = {
            o['order__id']: o['grosssum'] for o in
            OrderFee.objects.values('tax_rate', 'order__id').order_by().annotate(grosssum=Sum('value'))
        }
        fee_sum_cache = {
            (o['order__id'], o['tax_rate']): o for o in
            OrderFee.objects.values('tax_rate', 'order__id').order_by().annotate(
                taxsum=Sum('tax_value'), grosssum=Sum('value')
            )
        }
        sum_cache = {
            (o['order__id'], o['tax_rate']): o for o in
            OrderPosition.objects.values('tax_rate', 'order__id').order_by().annotate(
                taxsum=Sum('tax_value'), grosssum=Sum('price')
            )
        }

        for order in qs.order_by('datetime'):
            row = [
                order.code,
                localize(order.total),
                order.get_status_display(),
                order.email,
                order.datetime.astimezone(tz).strftime('%Y-%m-%d'),
            ]
            try:
                row += [
                    order.invoice_address.company,
                    order.invoice_address.name,
                    order.invoice_address.street,
                    order.invoice_address.zipcode,
                    order.invoice_address.city,
                    order.invoice_address.country if order.invoice_address.country else
                    order.invoice_address.country_old,
                    order.invoice_address.vat_id,
                ]
            except InvoiceAddress.DoesNotExist:
                row += ['', '', '', '', '', '', '']

            row += [
                order.payment_date.astimezone(tz).strftime('%Y-%m-%d') if order.payment_date else '',
                localize(full_fee_sum_cache.get(order.id) or Decimal('0.00')),
                order.locale,
            ]

            for tr in tax_rates:
                taxrate_values = sum_cache.get((order.id, tr), {'grosssum': Decimal('0.00'), 'taxsum': Decimal('0.00')})
                fee_taxrate_values = fee_sum_cache.get((order.id, tr),
                                                       {'grosssum': Decimal('0.00'), 'taxsum': Decimal('0.00')})

                row += [
                    localize(taxrate_values['grosssum'] + fee_taxrate_values['grosssum']),
                    localize(taxrate_values['grosssum'] - taxrate_values['taxsum']
                             + fee_taxrate_values['grosssum'] - fee_taxrate_values['taxsum']),
                    localize(taxrate_values['taxsum'] + fee_taxrate_values['taxsum']),
                ]

            row.append(', '.join([i.number for i in order.invoices.all()]))
            writer.writerow(row)

        return '{}_orders.csv'.format(self.event.slug), 'text/csv', output.getvalue().encode("utf-8")


class PaymentListExporter(BaseExporter):
    identifier = 'paymentlistcsv'
    verbose_name = ugettext_lazy('List of payments and refunds (CSV)')

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('successful_only',
                 forms.BooleanField(
                     label=_('Only successful payments'),
                     initial=True,
                     required=False
                 )),
            ]
        )

    def render(self, form_data: dict):
        output = io.StringIO()
        tz = pytz.timezone(self.event.settings.timezone)
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        provider_names = {
            k: v.verbose_name
            for k, v in self.event.get_payment_providers().items()
        }

        payments = OrderPayment.objects.filter(
            order__event=self.event,
        ).order_by('created')
        refunds = OrderRefund.objects.filter(
            order__event=self.event
        ).order_by('created')

        if form_data['successful_only']:
            payments = payments.filter(
                state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            )
            refunds = refunds.filter(
                state=OrderRefund.REFUND_STATE_DONE,
            )

        objs = sorted(list(payments) + list(refunds), key=lambda o: o.created)

        headers = [
            _('Order'), _('Payment ID'), _('Creation date'), _('Completion date'), _('Status'),
            _('Amount'), _('Payment method')
        ]
        writer.writerow(headers)

        for obj in objs:
            if isinstance(obj, OrderPayment) and obj.payment_date:
                d2 = obj.payment_date.astimezone(tz).date().strftime('%Y-%m-%d')
            elif isinstance(obj, OrderRefund) and obj.execution_date:
                d2 = obj.execution_date.astimezone(tz).date().strftime('%Y-%m-%d')
            else:
                d2 = ''
            row = [
                obj.order.code,
                obj.full_id,
                obj.created.astimezone(tz).date().strftime('%Y-%m-%d'),
                d2,
                obj.get_state_display(),
                localize(obj.amount * (-1 if isinstance(obj, OrderRefund) else 1)),
                provider_names.get(obj.provider, obj.provider)
            ]
            writer.writerow(row)

        return '{}_payments.csv'.format(self.event.slug), 'text/csv', output.getvalue().encode("utf-8")


class QuotaListExporter(BaseExporter):
    identifier = 'quotalistcsv'
    verbose_name = ugettext_lazy('Quota availabilities (CSV)')

    def render(self, form_data: dict):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        headers = [
            _('Quota name'), _('Total quota'), _('Paid orders'), _('Pending orders'), _('Blocking vouchers'),
            _('Current user\'s carts'), _('Waiting list'), _('Current availability')
        ]
        writer.writerow(headers)

        for quota in self.event.quotas.all():
            avail = quota.availability()
            row = [
                quota.name,
                _('Infinite') if quota.size is None else quota.size,
                quota.count_paid_orders(),
                quota.count_pending_orders(),
                quota.count_blocking_vouchers(),
                quota.count_in_cart(),
                quota.count_waiting_list_pending(),
                _('Infinite') if avail[1] is None else avail[1]
            ]
            writer.writerow(row)

        return '{}_quotas.csv'.format(self.event.slug), 'text/csv', output.getvalue().encode("utf-8")


@receiver(register_data_exporters, dispatch_uid="exporter_orderlist")
def register_orderlist_exporter(sender, **kwargs):
    return OrderListExporter


@receiver(register_data_exporters, dispatch_uid="exporter_paymentlist")
def register_paymentlist_exporter(sender, **kwargs):
    return PaymentListExporter


@receiver(register_data_exporters, dispatch_uid="exporter_quotalist")
def register_quotalist_exporter(sender, **kwargs):
    return QuotaListExporter
