import calendar
from datetime import date, timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import EmailTemplate, Invoice, InvoiceLine, PaymentReminder, RecurringInvoiceSchedule, ReminderPolicy

DEFAULT_TEMPLATES={
    EmailTemplate.Kind.REMINDER1:('Herinnering factuur {{ factuurnummer }}','Beste {{ klantnaam }},\n\nDe betalingstermijn van factuur {{ factuurnummer }} is verstreken. Het openstaande bedrag is € {{ bedrag }}.'),
    EmailTemplate.Kind.REMINDER2:('Tweede herinnering factuur {{ factuurnummer }}','Beste {{ klantnaam }},\n\nWij hebben nog geen volledige betaling ontvangen voor factuur {{ factuurnummer }}. Openstaand: € {{ bedrag }}.'),
    EmailTemplate.Kind.REMINDER_FINAL:('Laatste herinnering factuur {{ factuurnummer }}','Beste {{ klantnaam }},\n\nDit is de laatste herinnering voor factuur {{ factuurnummer }}. Openstaand: € {{ bedrag }}.'),
}

def add_months(value,months):
    month=value.month-1+months; year=value.year+month//12; month=month%12+1
    return date(year,month,min(value.day,calendar.monthrange(year,month)[1]))

def generate_recurring_drafts(today=None):
    today=today or timezone.localdate(); created=[]
    for schedule_id in RecurringInvoiceSchedule.objects.filter(is_active=True,next_run__lte=today).values_list('id',flat=True):
        with transaction.atomic():
            schedule=RecurringInvoiceSchedule.objects.select_for_update().select_related('customer','organization','created_by').get(pk=schedule_id)
            if not schedule.is_active or schedule.next_run>today: continue
            invoice=Invoice.objects.create(organization=schedule.organization,customer=schedule.customer,created_by=schedule.created_by,title=schedule.title,issue_date=today,delivery_date=today,due_date=today+timedelta(days=schedule.payment_term_days),notes=schedule.notes or schedule.organization.default_invoice_notes)
            for position,line in enumerate(schedule.lines,1): InvoiceLine.objects.create(organization=schedule.organization,invoice=invoice,position=position,description=line['description'],quantity=Decimal(line['quantity']),unit=line.get('unit','stuk'),unit_price=Decimal(line['unit_price']),vat_rate=Decimal(str(line.get('vat_rate',21))))
            months={'monthly':1,'quarterly':3,'yearly':12}[schedule.frequency]; schedule.next_run=add_months(schedule.next_run,months); schedule.last_generated_at=timezone.now(); schedule.save(update_fields=['next_run','last_generated_at']); created.append(invoice)
    return created

def render_template(text,invoice):
    values={'{{ klantnaam }}':str(invoice.customer),'{{ factuurnummer }}':invoice.number or 'concept','{{ bedrag }}':f'{invoice.outstanding:.2f}','{{ vervaldatum }}':invoice.due_date.strftime('%d-%m-%Y')}
    for key,value in values.items(): text=text.replace(key,value)
    return text

def queue_payment_reminders(today=None):
    today=today or timezone.localdate(); queued=[]
    for policy in ReminderPolicy.objects.filter(enabled=True).select_related('organization'):
        invoices=policy.organization.invoices.filter(is_archived=False,status__in=[Invoice.Status.SENT,Invoice.Status.PARTIAL,Invoice.Status.OVERDUE],due_date__lt=today).select_related('customer').prefetch_related('lines','payments')
        for invoice in invoices:
            if invoice.outstanding<=0 or not invoice.customer.email: continue
            age=(today-invoice.due_date).days; level=3 if age>=policy.final_after_days else 2 if age>=policy.second_after_days else 1 if age>=policy.first_after_days else 0
            if not level or invoice.reminders.filter(level=level).exists(): continue
            kind={1:EmailTemplate.Kind.REMINDER1,2:EmailTemplate.Kind.REMINDER2,3:EmailTemplate.Kind.REMINDER_FINAL}[level]; subject,body=DEFAULT_TEMPLATES[kind]; template=policy.organization.email_templates.filter(kind=kind).first()
            if template: subject,body=template.subject,template.body
            queued.append(PaymentReminder.objects.create(organization=policy.organization,invoice=invoice,level=level,recipient=invoice.customer.email,subject=render_template(subject,invoice),body=render_template(body,invoice)))
    return queued
