from django.conf import settings
from django.db import models


class Plan(models.Model):
    """
    A pricing tier, fully managed from Django admin — no code changes
    needed to add a plan or flip which features it includes. Feature access
    is deliberately plain boolean flags (not a numeric-cap system): a
    feature is either in a plan or it isn't. Add a new BooleanField here
    whenever a new feature needs gating; see restaurants.decorators.plan_required
    for how a view checks one.
    """
    name = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.CharField(max_length=255, blank=True)

    # Core order-taking (New Order, Kitchen, History, Dashboard, Manage
    # Menu, Manage Users) is available on every plan — it's the product,
    # not an upsell — so there's no flag for it here. Offline order-taking
    # is likewise ungated on every plan (core reliability, not a premium
    # feature). Inventory is the first real plan-gated feature:
    has_inventory = models.BooleanField(
        default=False,
        help_text='Stock tracking, adjustments, and movement history (the Inventory screen).',
    )

    sort_order = models.PositiveIntegerField(default=0, help_text='Controls display order, e.g. in a pricing table.')
    is_active = models.BooleanField(default=True, help_text='Uncheck to retire a plan without deleting it (existing tenants keep it).')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'price']

    def __str__(self):
        return f'{self.name} (Rs. {self.price})'


class Restaurant(models.Model):
    """
    One row per tenant business (SaaS multi-tenant: each restaurant that
    signs up gets one of these). Every UserProfile belongs to exactly one
    Restaurant, and everything the app shows/writes is scoped through that
    link — see restaurants.middleware.TenantMiddleware, which resolves
    request.restaurant once per request from request.user.profile.
    """
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name='restaurants',
        help_text='Determines which gated features (e.g. Inventory) this tenant can access.',
    )
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    logo = models.ImageField(upload_to='restaurant_logos/', blank=True, null=True)

    currency_symbol = models.CharField(max_length=5, default='Rs.')
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    receipt_footer_note = models.CharField(
        max_length=255, blank=True, default='Thank you for your order!'
    )

    invoice_prefix = models.CharField(max_length=10, blank=True, default='INV')
    next_invoice_number = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def reserve_invoice_number(self):
        """Atomically claim the next invoice number for this restaurant."""
        from django.db.models import F
        Restaurant.objects.filter(pk=self.pk).update(
            next_invoice_number=F('next_invoice_number') + 1
        )
        self.refresh_from_db(fields=['next_invoice_number'])
        return self.next_invoice_number - 1

    def has_feature(self, feature_flag):
        """
        e.g. restaurant.has_feature('has_inventory'). A thin wrapper around
        the plan's boolean flag so callers don't need to know/import Plan
        directly — see restaurants.decorators.plan_required for the view-level
        enforcement built on top of this.
        """
        return bool(getattr(self.plan, feature_flag, False))


class UserProfile(models.Model):
    """
    Extends Django's built-in User with a POS-specific role. Every login-
    capable staff account has exactly one profile; created automatically
    for the first superuser via a data migration, and for every user
    created afterward through the Manage Users screen.
    """
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        CASHIER = 'cashier', 'Cashier'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile'
    )
    # One user belongs to exactly one restaurant (tenant). If the same
    # person needs to work at two separate restaurants, they get two
    # separate user accounts — deliberately not a many-to-many, since
    # tenants are onboarded manually and this keeps every permission check
    # a single unambiguous FK lookup rather than "which restaurant is
    # active right now for this multi-tenant user".
    restaurant = models.ForeignKey(
        'restaurants.Restaurant', on_delete=models.CASCADE, related_name='staff'
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CASHIER)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER
