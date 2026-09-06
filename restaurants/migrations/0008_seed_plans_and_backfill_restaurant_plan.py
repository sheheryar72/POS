from django.db import migrations


def seed_plans_and_backfill(apps, schema_editor):
    """
    Creates the two starting plans. Inventory wasn't plan-gated before this
    migration — every tenant that existed already had full access to it. To
    avoid silently taking that access away from a restaurant actively using
    Inventory, any existing restaurant that has real stock-tracked variants
    or recorded stock movements is backfilled onto Premium; every other
    pre-existing restaurant (never touched Inventory) goes on Basic, which
    matches what they were actually using.
    """
    Plan = apps.get_model('restaurants', 'Plan')
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    ItemVariant = apps.get_model('menu', 'ItemVariant')
    StockMovement = apps.get_model('menu', 'StockMovement')

    basic, _ = Plan.objects.get_or_create(
        name='Basic',
        defaults={
            'price': 0,
            'description': 'Core order-taking: New Order, Kitchen, History, Dashboard, Manage Menu, Manage Users.',
            'has_inventory': False,
            'sort_order': 0,
        },
    )
    premium, _ = Plan.objects.get_or_create(
        name='Premium',
        defaults={
            'price': 0,
            'description': 'Everything in Basic, plus Inventory (stock tracking, adjustments, movement history).',
            'has_inventory': True,
            'sort_order': 1,
        },
    )

    restaurant_ids_using_inventory = set(
        ItemVariant.objects.filter(
            track_stock=True, item__category__restaurant__isnull=False
        ).values_list('item__category__restaurant_id', flat=True)
    ) | set(
        StockMovement.objects.filter(
            variant__item__category__restaurant__isnull=False
        ).values_list('variant__item__category__restaurant_id', flat=True)
    )

    Restaurant.objects.filter(
        plan__isnull=True, id__in=restaurant_ids_using_inventory
    ).update(plan=premium)
    Restaurant.objects.filter(plan__isnull=True).update(plan=basic)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0007_plan_and_restaurant_plan_nullable'),
    ]

    operations = [
        migrations.RunPython(seed_plans_and_backfill, noop_reverse),
    ]
