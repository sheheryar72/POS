from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from menu.models import Category, ItemVariant, MenuItem
from restaurants.models import Restaurant

# Demo catalog for a retail/grocery-mart tenant (e.g. "City Mart"), for
# sales demos. Prices are realistic current Pakistani retail pricing (PKR)
# researched September 2026 — some individual entries are estimated from
# adjacent pack sizes/brands where an exact current listing wasn't found;
# still representative for demo purposes, not live inventory data.
# Each entry: (category name, [(item name, [(variant name, price), ...]), ...])
CATALOG = [
    ('Beverages', [
        ('Coca-Cola', [('1.5L Bottle', 190), ('500ml Bottle', 100)]),
        ('Pepsi', [('1.5L Bottle', 190)]),
        ('Sprite', [('1.5L Bottle', 190), ('345ml Can', 100)]),
        ('Nestle Pure Life Water', [('1.5L Bottle', 90), ('500ml Bottle', 50)]),
        ('Aquafina Water', [('1.5L Bottle', 85)]),
        ('Sting Energy Drink', [('250ml Can', 100)]),
        ('Nescafe Classic Coffee', [('50g Jar', 379)]),
        ('Lipton Yellow Label Tea', [('190g Pack', 460)]),
        ('Tapal Danedar Tea', [('190g Pack', 380)]),
        ('Shezan Juice', [('250ml Box', 80)]),
    ]),
    ('Snacks & Biscuits', [
        ('Lays Salted Chips', [('65g Packet', 50)]),
        ('Lays Masala Chips', [('Small Pack', 20)]),
        ('Kurkure Masala Munch', [('60g Packet', 50)]),
        ('Peek Freans Sooper', [('Family Pack', 120), ('Single Pack', 30)]),
        ('LU Prince Biscuits', [('Family Pack', 100)]),
        ('LU Rio Biscuits', [('24 Ticky Box', 480)]),
        ('Cadbury Dairy Milk', [('36g Bar', 148), ('100g Bar', 380)]),
        ('Cadbury Fruit & Nut', [('38g Bar', 195)]),
        ('Nimko / Namkeen Mix', [('200g Pack', 150)]),
        ('Kolson Chanay Zor Garam', [('150g Pack', 100)]),
    ]),
    ('Grocery & Staples', [
        ('Falak Select Basmati Rice', [('1kg', 430)]),
        ('Guard Basmati Rice', [('1kg', 400)]),
        ('Super Kernel Basmati Rice', [('1kg', 420)]),
        ('Sunridge Atta', [('10kg Bag', 890)]),
        ('Premium Fine Atta', [('5kg Bag', 950)]),
        ('Sugar', [('1kg', 150)]),
        ('Dalda Cooking Oil', [('1L Pouch', 515)]),
        ('Sufi Cooking Oil', [('1L', 680)]),
        ('Masoor Daal', [('1kg', 275)]),
        ('Chana Daal', [('1kg', 267)]),
        ('Moong Daal', [('1kg', 430)]),
        ('Shan Masala (Biryani/Karahi)', [('50g Packet', 90)]),
    ]),
    ('Dairy & Bakery', [
        ('Olpers Full Cream Milk', [('1L Pack', 365), ('250ml Pack', 95)]),
        ('Nestle Milk Pack', [('1L', 370)]),
        ('Haleeb Milk', [('1L', 360)]),
        ('Nurpur Yogurt', [('1kg Tub', 280)]),
        ('Butter', [('200g', 450)]),
        ('Dayfresh Cheddar Cheese Slices', [('10s Pack', 565)]),
        ('Sliced Bread', [('Large Loaf', 180)]),
        ('Eggs', [('1 Dozen', 313), ('Half Dozen', 160)]),
    ]),
    ('Household & Personal Care', [
        ('Lux Soap', [('3-Pack', 450)]),
        ('Safeguard Soap', [('Single Bar', 180)]),
        ('Sunsilk Shampoo', [('200ml', 279)]),
        ('Head & Shoulders Shampoo', [('200ml', 550)]),
        ('Surf Excel Detergent Powder', [('2kg', 999), ('3kg', 1480)]),
        ('Surf Excel Liquid Detergent', [('500ml', 389)]),
        ('Ariel Detergent Powder', [('1kg', 420)]),
        ('Colgate Toothpaste', [('100g Tube', 220)]),
        ('Tissue Paper', [('Facial Box', 270)]),
        ('Toilet Paper Roll', [('Single Roll', 70)]),
        ('Lemon Max Dishwashing Liquid', [('475ml', 399)]),
    ]),
]


class Command(BaseCommand):
    help = (
        'Seeds a retail/grocery-mart demo tenant\'s Category/MenuItem/ItemVariant '
        'rows with a realistic grocery catalog (~58 items, current PKR pricing) '
        'for sales demos. Safe to re-run: existing categories/items/variants are '
        'matched by name and updated in place rather than duplicated.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--restaurant-name', required=True,
            help='Exact name of the Restaurant (tenant) to seed, e.g. "City Mart"',
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
            for cat_index, (cat_name, items) in enumerate(CATALOG):
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
