from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[('core','0016_organization_default_invoice_notes_and_more')]
    operations=[migrations.AddField(model_name='customer',name='archived_at',field=models.DateTimeField(blank=True,null=True)),migrations.AddField(model_name='customer',name='archived_by',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='archived_customers',to='core.user'))]
