from django.db import migrations


def migrate_city_data(apps, schema_editor):
    Client = apps.get_model('clients', 'Client')
    City = apps.get_model('masters', 'City')

    cities_by_name = {}
    for client in Client.objects.exclude(city__isnull=True).exclude(city__exact=''):
        name = client.city.strip()
        if not name:
            continue
        key = name.lower()
        city = cities_by_name.get(key)
        if city is None:
            city, _ = City.objects.get_or_create(
                name__iexact=name,
                defaults={'name': name},
            )
            cities_by_name[key] = city
        client.city_fk = city
        client.save(update_fields=['city_fk'])


def reverse_city_data(apps, schema_editor):
    Client = apps.get_model('clients', 'Client')
    for client in Client.objects.exclude(city_fk__isnull=True):
        client.city = client.city_fk.name
        client.save(update_fields=['city'])


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0002_client_city_fk'),
    ]

    operations = [
        migrations.RunPython(migrate_city_data, reverse_city_data),
    ]
