from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0005_backfill_userprofile_restaurant'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='restaurant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='staff', to='restaurants.restaurant',
            ),
        ),
    ]
