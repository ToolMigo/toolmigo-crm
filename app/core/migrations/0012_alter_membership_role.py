from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0011_emaildelivery_archived_at_emaildelivery_archived_by_and_more')]

    operations = [
        migrations.AlterField(
            model_name='membership',
            name='role',
            field=models.CharField(
                choices=[
                    ('owner', 'Bedrijfsbeheerder'),
                    ('approver', 'Facturatie'),
                    ('employee', 'Medewerker'),
                    ('sales', 'Verkoop'),
                    ('customer_manager', 'Klantbeheer'),
                    ('planner', 'Planning'),
                    ('project_manager', 'Projectbeheer'),
                    ('support', 'Support'),
                ],
                default='employee',
                max_length=20,
            ),
        ),
    ]
