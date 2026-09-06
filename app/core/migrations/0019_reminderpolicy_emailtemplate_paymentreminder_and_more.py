import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_project_mileageentry_expense_projectdocument_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReminderPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=False)),
                ('first_after_days', models.PositiveSmallIntegerField(default=1)),
                ('second_after_days', models.PositiveSmallIntegerField(default=7)),
                ('final_after_days', models.PositiveSmallIntegerField(default=14)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='reminder_policy', to='core.organization')),
            ],
        ),
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('quote', 'Offerte'), ('invoice', 'Factuur'), ('reminder1', 'Eerste herinnering'), ('reminder2', 'Tweede herinnering'), ('reminder_final', 'Laatste herinnering')], max_length=20)),
                ('subject', models.CharField(max_length=250)),
                ('body', models.TextField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_templates', to='core.organization')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('organization', 'kind'), name='unique_org_email_template')],
            },
        ),
        migrations.CreateModel(
            name='PaymentReminder',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('level', models.PositiveSmallIntegerField()),
                ('recipient', models.EmailField(max_length=254)),
                ('subject', models.CharField(max_length=250)),
                ('body', models.TextField()),
                ('status', models.CharField(choices=[('queued', 'In wachtrij'), ('sent', 'Verzonden'), ('failed', 'Mislukt')], default='queued', max_length=10)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reminders', to='core.invoice')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_reminders', to='core.organization')),
            ],
            options={
                'ordering': ['-created_at'],
                'constraints': [models.UniqueConstraint(fields=('invoice', 'level'), name='unique_invoice_reminder_level')],
            },
        ),
        migrations.CreateModel(
            name='RecurringInvoiceSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('frequency', models.CharField(choices=[('monthly', 'Maandelijks'), ('quarterly', 'Per kwartaal'), ('yearly', 'Jaarlijks')], default='monthly', max_length=12)),
                ('next_run', models.DateField(db_index=True)),
                ('payment_term_days', models.PositiveSmallIntegerField(default=14)),
                ('lines', models.JSONField(default=list)),
                ('notes', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('last_generated_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recurring_invoice_schedules', to='core.customer')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recurring_invoice_schedules', to='core.organization')),
            ],
            options={
                'ordering': ['next_run'],
                'indexes': [models.Index(fields=['organization', 'is_active', 'next_run'], name='core_recurr_organiz_abe006_idx')],
            },
        ),
    ]
