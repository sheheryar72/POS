import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0008_seed_plans_and_backfill_restaurant_plan'),
    ]

    operations = [
        migrations.AlterField(
            model_name='restaurant',
            name='plan',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='restaurants', to='restaurants.plan',
                help_text='Determines which gated features (e.g. Inventory) this tenant can access.',
            ),
        ),
    ]
