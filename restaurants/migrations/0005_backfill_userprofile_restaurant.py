from django.db import migrations


def backfill_restaurant(apps, schema_editor):
    """
    Every deployment that existed before multi-tenancy had exactly one
    Restaurant row (the single-tenant assumption). Link every existing
    UserProfile to it, so no current staff account loses access when this
    migration runs. If somehow no Restaurant exists yet (a brand-new,
    never-seeded deployment), create a placeholder rather than leaving
    profiles dangling with a null tenant.
    """
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    UserProfile = apps.get_model('restaurants', 'UserProfile')

    restaurant = Restaurant.objects.first()
    if restaurant is None:
        restaurant = Restaurant.objects.create(name='My Restaurant')

    UserProfile.objects.filter(restaurant__isnull=True).update(restaurant=restaurant)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0004_userprofile_restaurant_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill_restaurant, noop_reverse),
    ]
