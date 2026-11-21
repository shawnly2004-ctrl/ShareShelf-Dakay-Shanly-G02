from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('items', '0004_borrowrequest'),
    ]

    operations = [
        migrations.CreateModel(
            name='HandoffConfirmation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('handoff_type', models.CharField(choices=[('pickup', 'Pickup'), ('return', 'Return')], max_length=10)),
                ('lender_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('borrower_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='handoffs', to='items.borrowrequest')),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(
                        fields=('request', 'handoff_type'),
                        name='unique_request_handoff_type',
                    ),
                ],
            },
        ),
    ]
