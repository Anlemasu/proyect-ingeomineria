from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trips', '0004_trip_pending_debt_justification'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='observations',
            field=models.TextField(blank=True, null=True),
        ),
    ]
