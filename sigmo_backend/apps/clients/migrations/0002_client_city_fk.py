import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0001_initial'),
        ('masters', '0004_city'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='city_fk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, to='masters.city'),
        ),
    ]
