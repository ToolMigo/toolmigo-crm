from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[('core','0013_membership_removal_fields')]
    operations=[migrations.CreateModel(name='BackupConfiguration',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('max_backups',models.PositiveSmallIntegerField(default=10)),('automatic_enabled',models.BooleanField(default=False)),('frequency',models.CharField(choices=[('daily','Dagelijks'),('weekly','Wekelijks')],default='daily',max_length=10)),('weekday',models.PositiveSmallIntegerField(default=0)),('run_at',models.TimeField(default='02:00')),('last_run_date',models.DateField(blank=True,null=True)),('updated_at',models.DateTimeField(auto_now=True))])]
