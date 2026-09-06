from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0003_backfill_owner_profiles'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='restaurant',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='staff', to='restaurants.restaurant',
            ),
        ),
    ]
