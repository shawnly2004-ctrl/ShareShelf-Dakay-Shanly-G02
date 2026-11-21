from django.db import migrations, models
import django.db.models.deletion


def assign_default_community(apps, schema_editor):
    Community = apps.get_model('accounts', 'Community')
    User = apps.get_model('accounts', 'User')
    community = Community.objects.filter(name='Cebu City').first()
    if community is None:
        community = Community.objects.first()
    if community is not None:
        User.objects.filter(community__isnull=True).update(community=community)


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_user_rating_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='address_detail',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='user',
            name='failed_login_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='user',
            name='language_pref',
            field=models.CharField(choices=[('en', 'English'), ('fil', 'Filipino')], default='en', max_length=3),
        ),
        migrations.AddField(
            model_name='user',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.RunPython(assign_default_community, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='community',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='residents', to='accounts.community'),
        ),
    ]
