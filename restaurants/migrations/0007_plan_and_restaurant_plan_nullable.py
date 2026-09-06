import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0006_userprofile_restaurant_required'),
    ]

    operations = [
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('price', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('has_inventory', models.BooleanField(
                    default=False,
                    help_text='Stock tracking, adjustments, and movement history (the Inventory screen).',
                )),
                ('sort_order', models.PositiveIntegerField(default=0, help_text='Controls display order, e.g. in a pricing table.')),
                ('is_active', models.BooleanField(default=True, help_text='Uncheck to retire a plan without deleting it (existing tenants keep it).')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['sort_order', 'price'],
            },
        ),
        migrations.AddField(
            model_name='restaurant',
            name='plan',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='restaurants', to='restaurants.plan',
                help_text='Determines which gated features (e.g. Inventory) this tenant can access.',
            ),
        ),
    ]
