from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0003_migrate_city_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='client',
            name='city',
        ),
        migrations.RenameField(
            model_name='client',
            old_name='city_fk',
            new_name='city',
        ),
    ]
