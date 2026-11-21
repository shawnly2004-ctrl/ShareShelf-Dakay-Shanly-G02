from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('items', '0005_handoffconfirmation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Rating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.PositiveSmallIntegerField()),
                ('review_text', models.CharField(blank=True, max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings', to='items.borrowrequest')),
                ('rater', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings_given', to=settings.AUTH_USER_MODEL)),
                ('ratee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='rating',
            constraint=models.CheckConstraint(
                condition=models.Q(('score__gte', 1), ('score__lte', 5)),
                name='rating_score_between_1_and_5',
            ),
        ),
        migrations.AddConstraint(
            model_name='rating',
            constraint=models.CheckConstraint(
                condition=~models.Q(('rater', models.F('ratee'))),
                name='rating_rater_not_ratee',
            ),
        ),
        migrations.AddConstraint(
            model_name='rating',
            constraint=models.UniqueConstraint(
                fields=('request', 'rater'),
                name='unique_request_rater',
            ),
        ),
    ]
