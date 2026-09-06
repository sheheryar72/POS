from django.conf import settings
from django.db import models


class Category(models.Model):
    # Every category belongs to exactly one restaurant (tenant). MenuItem
    # and ItemVariant deliberately do NOT repeat this FK — they scope
    # transitively through category/item, so there's exactly one place a
    # row's tenant is recorded and no risk of it drifting out of sync.
    restaurant = models.ForeignKey(
        'restaurants.Restaurant', on_delete=models.CASCADE, related_name='categories'
    )
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class ItemVariant(models.Model):
    """
    Every menu item has at least one variant (e.g. 'Regular').
    Items with sizes (Half/Full) just get multiple variants, each priced independently.
    """
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=50, default='Regular')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    # Inventory is opt-in per variant: a made-to-order restaurant dish can
    # leave this off entirely (behaves exactly as before — unlimited),
    # while a retail shop turns it on for stock-counted products. Adjustments
    # only ever happen through StockMovement (see below) so every change to
    # stock_quantity has an audit trail — nothing should write to this field
    # directly outside of that ledger logic.
    track_stock = models.BooleanField(default=False)
    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'price']
        unique_together = ('item', 'name')

    def __str__(self):
        return f'{self.item.name} - {self.name}'

    @property
    def is_out_of_stock(self):
        return self.track_stock and self.stock_quantity <= 0

    @property
    def is_low_stock(self):
        return self.track_stock and 0 < self.stock_quantity <= self.low_stock_threshold

    def record_movement(self, movement_type, quantity_change, note='', order_line=None, user=None):
        """
        The only sanctioned way to change stock_quantity. Locks this variant's
        row (select_for_update), applies the change, writes the resulting
        count, and appends a StockMovement — all inside the caller's
        transaction. Safe to call even when track_stock is False (no-ops on
        the quantity but still worth guarding against by the caller, since a
        movement on an untracked variant wouldn't make sense).
        """
        from django.db import transaction

        with transaction.atomic():
            variant = ItemVariant.objects.select_for_update().get(pk=self.pk)
            variant.stock_quantity += quantity_change
            variant.save(update_fields=['stock_quantity'])
            movement = StockMovement.objects.create(
                variant=variant,
                movement_type=movement_type,
                quantity_change=quantity_change,
                resulting_quantity=variant.stock_quantity,
                note=note[:255],
                order_line=order_line,
                created_by=user,
            )
        self.stock_quantity = variant.stock_quantity
        return movement


class StockMovement(models.Model):
    """
    Append-only ledger of every change to a variant's stock_quantity — sales
    (negative), purchases (positive), and manual adjustments (either sign).
    stock_quantity on ItemVariant is a derived cache of "sum of all
    movements"; it's updated atomically alongside each movement being
    created, but this table is the source of truth for history/audit.
    """
    class MovementType(models.TextChoices):
        SALE = 'sale', 'Sale'
        PURCHASE = 'purchase', 'Purchase'
        ADJUSTMENT = 'adjustment', 'Adjustment'

    variant = models.ForeignKey(ItemVariant, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity_change = models.IntegerField(help_text='Positive for stock in, negative for stock out.')
    resulting_quantity = models.IntegerField(help_text='stock_quantity snapshot immediately after this movement.')
    note = models.CharField(max_length=255, blank=True)

    order_line = models.ForeignKey(
        'orders.OrderLine', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements',
        help_text='Set when movement_type is "sale" — links back to the order line that caused it.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.variant} {self.movement_type} {self.quantity_change:+d}'
