from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0022_workorder_photo')]
    operations = [
        migrations.AddField(
            model_name='documenttemplate',
            name='layout',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
