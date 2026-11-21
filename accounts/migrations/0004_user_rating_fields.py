from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_seed_communities'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='account_status',
            field=models.CharField(choices=[('active', 'Active'), ('flagged', 'Flagged')], default='active', max_length=20),
        ),
        migrations.AddField(
            model_name='user',
            name='avg_rating',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=3, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='rating_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
