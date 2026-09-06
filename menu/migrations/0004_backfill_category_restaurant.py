from django.db import migrations


def backfill_restaurant(apps, schema_editor):
    """Same reasoning as restaurants.0005: one pre-existing Restaurant owns
    every category that existed before multi-tenancy."""
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    Category = apps.get_model('menu', 'Category')

    restaurant = Restaurant.objects.first()
    if restaurant is None:
        restaurant = Restaurant.objects.create(name='My Restaurant')

    Category.objects.filter(restaurant__isnull=True).update(restaurant=restaurant)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0003_category_restaurant_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill_restaurant, noop_reverse),
    ]
