import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_reminderpolicy_emailtemplate_paymentreminder_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectdocument',
            name='visible_to_portal',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='PortalAccess',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('token_digest', models.CharField(max_length=64, unique=True)),
                ('token_hint', models.CharField(max_length=12)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('contact', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portal_accesses', to='core.contact')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_portal_accesses', to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portal_accesses', to='core.customer')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portal_accesses', to='core.organization')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PortalDecision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('decision', models.CharField(choices=[('accepted', 'Geaccepteerd'), ('declined', 'Afgewezen')], max_length=10)),
                ('signer_name', models.CharField(max_length=200)),
                ('reason', models.TextField(blank=True)),
                ('document_sha256', models.CharField(max_length=64)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='portal_decisions', to='core.organization')),
                ('portal_access', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='decisions', to='core.portalaccess')),
                ('quote', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='portal_decision', to='core.quote')),
            ],
        ),
        migrations.AddIndex(
            model_name='portalaccess',
            index=models.Index(fields=['organization', 'customer', 'expires_at'], name='core_portal_organiz_13ddea_idx'),
        ),
    ]
