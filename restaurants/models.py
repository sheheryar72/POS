from django.db import models


class Restaurant(models.Model):
    """
    Single-tenant for now: one row = the restaurant using this deployment.
    Kept as a real table (not settings.py constants) so that going
    multi-tenant later is a matter of adding restaurant FKs elsewhere,
    not redesigning this model.
    """
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

    @classmethod
    def get_current(cls):
        """Single-tenant helper: returns the one restaurant, creating a default if missing."""
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create(name='My Restaurant')
        return obj

    def reserve_invoice_number(self):
        """Atomically claim the next invoice number for this restaurant."""
        from django.db.models import F
        Restaurant.objects.filter(pk=self.pk).update(
            next_invoice_number=F('next_invoice_number') + 1
        )
        self.refresh_from_db(fields=['next_invoice_number'])
        return self.next_invoice_number - 1
