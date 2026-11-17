from django.db import migrations


def seed(apps, schema_editor):
    Community = apps.get_model('accounts', 'Community')
    for name, barangay in [
        ("Lahug Community", "Lahug"),
        ("Guadalupe Community", "Guadalupe"),
        ("Mabolo Community", "Mabolo"),
    ]:
        Community.objects.get_or_create(
            name=name, defaults={'barangay': barangay, 'city': 'Cebu City'})


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_community_remove_user_barangay_user_community'),
    ]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]