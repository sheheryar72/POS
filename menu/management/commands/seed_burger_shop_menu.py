from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from menu.models import Category, ItemVariant, MenuItem
from restaurants.models import Restaurant

# Transcribed from the client's physical menu board (Super Burger & Star
# Juice). Single items only — the board's "Deal # N" combo meals (bundled
# item + drink + fries at one price) aren't represented because the current
# MenuItem/ItemVariant model has no concept of a multi-item bundle; those
# would need a separate feature before they can be added as real menu rows.
# Each entry: (category name, [(item name, [(variant name, price), ...]), ...])
MENU = [
    ('Bun Kabab', [
        ('Dall Egg Burger', [('Regular', 140)]),
        ('Special Egg Burger', [('Regular', 180)]),
        ('Aaloo Egg Burger', [('Regular', 130)]),
        ('Aaloo Burger', [('Regular', 180)]),
        ('Chicken Burger', [('Regular', 180)]),
        ('Chicken Egg Special Burger', [('Regular', 230)]),
        ('Chicken cheese Burger', [('Regular', 250)]),
        ('Chicken Egg Cheese Burger', [('Regular', 320)]),
        ('Chicken Jumbo Burger', [('Regular', 380)]),
    ]),
    ('Sandwich', [
        ('Club Sandwich', [('Regular', 390)]),
        ('Club Cheese Sandwich', [('Regular', 430)]),
        ('Chicken Sandwich', [('Regular', 350)]),
        ('Chicken Cheese Sandwich', [('Regular', 410)]),
        ('Chicken Sandwich 2 Pcs', [('Regular', 300)]),
        ('Vegetable Sandwich', [('Regular', 250)]),
        ('Special Super Club Sandwich', [('Regular', 630)]),
        ('Crispy Club Sandwich', [('Regular', 400)]),
        ('Double Egg Sandwich', [('Regular', 300)]),
    ]),
    ('Chicken Burger', [
        ('Chicken Burger', [('Regular', 390)]),
        ('Chicken Cheese Burger', [('Regular', 430)]),
        ('Special Burger', [('Regular', 550)]),
    ]),
    ('Zinger Burger', [
        ('Zinger Burger', [('Regular', 430)]),
        ('Zinger Cheese Burger', [('Regular', 470)]),
        ('Manchin Crispy Burger', [('Regular', 450)]),
        ('Spicy Grill Burger', [('Regular', 480)]),
        ('Super Special Zinger with (Leg pcs)', [('Regular', 600)]),
        ('MEGA Zinger', [('Regular', 630)]),
        ('MEGA Cheese Zinger', [('Regular', 680)]),
    ]),
    ('Wings', [
        ('Wings (6pcs)', [('Regular', 300)]),
        ('Garlic Wings (6pcs)', [('Regular', 350)]),
        ('Spicy wings (6pcs)', [('Regular', 320)]),
    ]),
    ('Fries', [
        ('Fries (Small) plate', [('Regular', 100)]),
        ('Fries Mayo plate', [('Regular', 150)]),
        ('Special Mayo plate', [('Regular', 200)]),
        ('Pizza Fries', [('Regular', 300)]),
    ]),
    ('Crispy Broast', [
        ('Quarter Leg Broast', [('Regular', 450)]),
        ('Quarter Chest Broast', [('Regular', 470)]),
        ('Half Broast', [('Regular', 900)]),
        ('Full Broast', [('Regular', 1800)]),
        ('Quarter spicy Broast', [('Regular', 480)]),
        ('Full Spicy Broast', [('Regular', 1850)]),
    ]),
    ('Biryani', [
        ('Chicken Biryani', [('Regular', 250)]),
        ('SADA Biryani', [('Regular', 200)]),
    ]),
    ('Milk Shakes', [
        ('Banana', [('Regular', 150)]),
        ('Mango', [('Regular', 240)]),
        ('Khajor', [('Regular', 250)]),
        ('Cheeko', [('Regular', 220)]),
        ('Strawberry', [('Regular', 250)]),
        ('Banana + Khajur', [('Regular', 200)]),
        ('Injeer + Khajur', [('Regular', 200)]),
        ('Banana + Cheeko', [('Regular', 250)]),
    ]),
    ('Fresh Juice', [
        ('Apple', [('Regular', 250)]),
        ('Anar', [('Regular', 400)]),
        ('Mosambi', [('Regular', 240)]),
        ('Orange', [('Regular', 250)]),
        ('Gray Fruit', [('Regular', 200)]),
        ('Falsa', [('Regular', 230)]),
        ('Peach', [('Regular', 200)]),
    ]),
]


class Command(BaseCommand):
    help = (
        'Seeds a tenant\'s Category/MenuItem/ItemVariant rows from the '
        'hardcoded Super Burger & Star Juice menu board. Safe to re-run: '
        'existing categories/items/variants are matched by name and updated '
        'in place rather than duplicated.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--restaurant-name', required=True,
            help='Exact name of the Restaurant (tenant) to seed, e.g. "Burger Shop"',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would be created/updated without writing anything.',
        )

    def handle(self, *args, **options):
        restaurant_name = options['restaurant_name'].strip()
        dry_run = options['dry_run']

        try:
            restaurant = Restaurant.objects.get(name__iexact=restaurant_name)
        except Restaurant.DoesNotExist:
            raise CommandError(
                f'No restaurant named "{restaurant_name}". Create it first '
                '(Django admin -> Restaurants -> Add Restaurant, or the '
                'create_tenant command).'
            )
        except Restaurant.MultipleObjectsReturned:
            raise CommandError(
                f'More than one restaurant is named "{restaurant_name}" — '
                'seed by id instead or rename one of them first.'
            )

        categories_created = categories_updated = 0
        items_created = items_updated = 0
        variants_created = variants_updated = 0

        with transaction.atomic():
            for cat_index, (cat_name, items) in enumerate(MENU):
                category, created = Category.objects.update_or_create(
                    restaurant=restaurant, name=cat_name,
                    defaults={'sort_order': cat_index, 'is_active': True},
                )
                categories_created += created
                categories_updated += not created

                for item_index, (item_name, variants) in enumerate(items):
                    item, created = MenuItem.objects.update_or_create(
                        category=category, name=item_name,
                        defaults={'sort_order': item_index, 'is_available': True},
                    )
                    items_created += created
                    items_updated += not created

                    for var_index, (var_name, price) in enumerate(variants):
                        _, created = ItemVariant.objects.update_or_create(
                            item=item, name=var_name,
                            defaults={'price': price, 'sort_order': var_index, 'is_available': True},
                        )
                        variants_created += created
                        variants_updated += not created

            if dry_run:
                transaction.set_rollback(True)

        prefix = '[DRY RUN] Would seed' if dry_run else 'Seeded'
        self.stdout.write(self.style.SUCCESS(
            f'{prefix} "{restaurant.name}": '
            f'{categories_created} categories created / {categories_updated} updated, '
            f'{items_created} items created / {items_updated} updated, '
            f'{variants_created} variants created / {variants_updated} updated.'
        ))
        self.stdout.write(
            'Note: the menu board\'s combo "Deal # N" meals were not loaded — '
            'the current model has no bundle/combo concept, only single items '
            'with priced variants. Add those manually as Category "Deals" with '
            'each combo as one item if you want them in the POS as-is.'
        )
