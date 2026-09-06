from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0012_alter_membership_role')]

    operations = [
        migrations.AddField(model_name='membership',name='is_removed',field=models.BooleanField(db_index=True,default=False)),
        migrations.AddField(model_name='membership',name='removed_at',field=models.DateTimeField(blank=True,null=True)),
        migrations.AddField(model_name='membership',name='removed_by',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='removed_memberships',to=settings.AUTH_USER_MODEL)),
    ]
