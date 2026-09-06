from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[('core','0014_backupconfiguration')]
    operations=[migrations.AddField(model_name='user',name='recovery_code_hashes',field=models.JSONField(blank=True,default=list)),migrations.AddField(model_name='user',name='totp_enabled',field=models.BooleanField(default=False)),migrations.AddField(model_name='user',name='totp_secret_encrypted',field=models.TextField(blank=True))]
