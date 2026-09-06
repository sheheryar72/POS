import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from restaurants.models import Plan, Restaurant, UserProfile

User = get_user_model()


def generate_password(length=14):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = (
        'Onboard a new client: creates a Restaurant (tenant) and its first '
        'Owner login. Safe to run non-interactively (e.g. from a deploy '
        'script) — nothing is created if any validation fails.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--restaurant-name', required=True, help="e.g. \"Pizza Palace\"")
        parser.add_argument('--username', required=True, help='Login username for the Owner account')
        parser.add_argument(
            '--password', required=False,
            help='Owner password. If omitted, a random one is generated and printed once.',
        )
        parser.add_argument('--currency-symbol', default='Rs.')
        parser.add_argument('--tax-percent', type=float, default=0)
        parser.add_argument('--invoice-prefix', default='INV', help='Short prefix for invoice numbers, e.g. "PP"')
        parser.add_argument(
            '--plan', required=False,
            help='Plan name (e.g. "Basic", "Premium") — see Plan objects in admin. '
                 'Defaults to the lowest-priced active plan if omitted.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Skip the confirmation prompt if a restaurant with this name already exists.',
        )

    def handle(self, *args, **options):
        restaurant_name = options['restaurant_name'].strip()
        username = options['username'].strip()
        password = options['password'] or generate_password()
        currency_symbol = options['currency_symbol']
        tax_percent = options['tax_percent']
        invoice_prefix = options['invoice_prefix'].strip()[:10] or 'INV'

        if not restaurant_name:
            raise CommandError('--restaurant-name cannot be empty.')
        if not username:
            raise CommandError('--username cannot be empty.')

        # Fail fast, before creating anything, on the same constraint the
        # Manage Users API enforces (usernames are globally unique even
        # though everything else is tenant-scoped).
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(f'Username "{username}" is already taken by another account.')

        existing = Restaurant.objects.filter(name__iexact=restaurant_name).first()
        if existing and not options['force']:
            raise CommandError(
                f'A restaurant named "{existing.name}" (id={existing.id}) already exists. '
                'Pass --force to create a new, separate tenant with the same name anyway '
                '(e.g. two unrelated clients happen to share a business name).'
            )

        if options['plan']:
            plan = Plan.objects.filter(name__iexact=options['plan']).first()
            if not plan:
                available = ', '.join(Plan.objects.values_list('name', flat=True)) or '(none configured yet)'
                raise CommandError(f'No plan named "{options["plan"]}". Available plans: {available}')
        else:
            plan = Plan.objects.filter(is_active=True).order_by('sort_order', 'price').first()
            if not plan:
                raise CommandError(
                    'No plans exist yet. Create at least one Plan in Django admin first '
                    '(Restaurants → Plans → Add), or pass --plan explicitly.'
                )

        with transaction.atomic():
            restaurant = Restaurant.objects.create(
                name=restaurant_name,
                plan=plan,
                currency_symbol=currency_symbol,
                tax_percent=tax_percent,
                invoice_prefix=invoice_prefix,
            )
            user = User.objects.create_user(username=username, password=password)
            UserProfile.objects.create(user=user, restaurant=restaurant, role=UserProfile.Role.OWNER)

        self.stdout.write(self.style.SUCCESS(
            f'\nCreated restaurant "{restaurant.name}" (id={restaurant.id}) on the "{plan.name}" plan '
            f'with Owner login "{username}".'
        ))
        if not options['password']:
            self.stdout.write(self.style.WARNING(
                f'Generated password (shown once, save it now): {password}'
            ))
        self.stdout.write(
            'Next: send the client their login URL + these credentials, and have '
            'them build their menu under Manage Menu.'
        )
