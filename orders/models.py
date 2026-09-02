from decimal import Decimal

from django.conf import settings
from django.db import models


class Order(models.Model):
    class OrderType(models.TextChoices):
        DINE_IN = 'dine_in', 'Dine-in'
        TAKEAWAY = 'takeaway', 'Takeaway'
        DELIVERY = 'delivery', 'Delivery'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    class DiscountType(models.TextChoices):
        NONE = 'none', 'None'
        FLAT = 'flat', 'Flat amount'
        PERCENT = 'percent', 'Percentage'

    restaurant = models.ForeignKey(
        'restaurants.Restaurant', on_delete=models.CASCADE, related_name='orders'
    )
    invoice_number = models.CharField(max_length=30, blank=True, db_index=True)

    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.DINE_IN)
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    delivery_address = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.NONE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    payment_method = models.CharField(
        max_length=20,
        choices=[('cash', 'Cash')],
        default='cash',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.invoice_number or f'Order #{self.pk}'

    @property
    def subtotal(self):
        return sum((line.line_total for line in self.lines.all()), Decimal('0.00'))

    @property
    def discount_amount(self):
        subtotal = self.subtotal
        if self.discount_type == self.DiscountType.FLAT:
            return min(self.discount_value, subtotal)
        if self.discount_type == self.DiscountType.PERCENT:
            return (subtotal * self.discount_value / Decimal('100')).quantize(Decimal('0.01'))
        return Decimal('0.00')

    @property
    def taxable_amount(self):
        return self.subtotal - self.discount_amount

    @property
    def tax_amount(self):
        return (self.taxable_amount * self.tax_percent / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def total(self):
        return self.taxable_amount + self.tax_amount


class OrderLine(models.Model):
    """
    Snapshots item/variant name & price at order time, so later menu edits
    (price changes, renames, deletions) never alter historical orders.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='lines')
    variant = models.ForeignKey(
        'menu.ItemVariant', on_delete=models.SET_NULL, null=True, blank=True
    )

    item_name = models.CharField(max_length=150)
    variant_name = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    note = models.CharField(max_length=255, blank=True)

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f'{self.quantity} x {self.item_name} ({self.variant_name})'
