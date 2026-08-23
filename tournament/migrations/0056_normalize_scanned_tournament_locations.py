from django.db import migrations

def normalize_existing_locations(apps, schema_editor):
    ScannedTournament = apps.get_model('tournament', 'ScannedTournament')
    from tournament.services.scout_service import normalize_locations

    for p in ScannedTournament.objects.all():
        if p.host_country:
            cleaned = normalize_locations(p.host_country)
            if cleaned != p.host_country:
                p.host_country = cleaned
                p.save(update_fields=['host_country'])

def reverse_func(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0055_merge_20260820_2133'),
    ]

    operations = [
        migrations.RunPython(normalize_existing_locations, reverse_func),
    ]
