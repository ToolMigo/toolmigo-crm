import core.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_customer_archived_at_customer_archived_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('status', models.CharField(choices=[('planned', 'Gepland'), ('active', 'Actief'), ('on_hold', 'Gepauzeerd'), ('completed', 'Afgerond'), ('cancelled', 'Geannuleerd')], db_index=True, default='planned', max_length=20)),
                ('budget', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='projects', to='core.customer')),
                ('members', models.ManyToManyField(blank=True, related_name='projects', to='core.membership')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='projects', to='core.organization')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='MileageEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField()),
                ('kilometers', models.DecimalField(decimal_places=2, max_digits=8)),
                ('rate', models.DecimalField(decimal_places=2, default=0.23, max_digits=6)),
                ('description', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='mileage_entries', to='core.membership')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mileage_entries', to='core.organization')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mileage_entries', to='core.project')),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField()),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('description', models.CharField(max_length=300)),
                ('receipt', models.FileField(blank=True, upload_to=core.models.expense_upload_path)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='expenses', to='core.membership')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expenses', to='core.organization')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expenses', to='core.project')),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
        migrations.CreateModel(
            name='ProjectDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('file', models.FileField(upload_to=core.models.project_document_path)),
                ('original_name', models.CharField(max_length=255)),
                ('content_type', models.CharField(blank=True, max_length=120)),
                ('size', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='core.customer')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='core.organization')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='core.project')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='uploaded_documents', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TimeEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField()),
                ('hours', models.DecimalField(decimal_places=2, max_digits=6)),
                ('hourly_rate', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('description', models.CharField(max_length=300)),
                ('status', models.CharField(choices=[('draft', 'Concept'), ('submitted', 'Ingediend'), ('approved', 'Goedgekeurd'), ('invoiced', 'Gefactureerd'), ('rejected', 'Afgewezen')], db_index=True, default='draft', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='approved_time_entries', to=settings.AUTH_USER_MODEL)),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='time_entries', to='core.invoice')),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='time_entries', to='core.membership')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_entries', to='core.organization')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_entries', to='core.project')),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Opportunity',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('stage', models.CharField(choices=[('lead', 'Lead'), ('qualified', 'Gekwalificeerd'), ('proposal', 'Voorstel'), ('negotiation', 'Onderhandeling'), ('won', 'Gewonnen'), ('lost', 'Verloren')], db_index=True, default='lead', max_length=20)),
                ('expected_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('probability', models.PositiveSmallIntegerField(default=10)),
                ('follow_up_date', models.DateField(blank=True, db_index=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opportunities', to='core.customer')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='opportunities', to='core.organization')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opportunities', to='core.membership')),
            ],
            options={
                'ordering': ['follow_up_date', '-created_at'],
                'indexes': [models.Index(fields=['organization', 'stage'], name='core_opport_organiz_395846_idx')],
            },
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['organization', 'status'], name='core_projec_organiz_89f076_idx'),
        ),
        migrations.AddConstraint(
            model_name='projectdocument',
            constraint=models.CheckConstraint(condition=models.Q(('project__isnull', False), ('customer__isnull', False), _connector='OR'), name='document_has_parent'),
        ),
        migrations.AddIndex(
            model_name='timeentry',
            index=models.Index(fields=['organization', 'status'], name='core_timeen_organiz_54368d_idx'),
        ),
    ]
