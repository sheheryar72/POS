from django.contrib import admin

from .models import Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ('item_name', 'variant_name', 'unit_price', 'quantity')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'order_type', 'status', 'total', 'created_at')
    list_filter = ('status', 'order_type', 'created_at')
    search_fields = ('invoice_number', 'customer_name', 'customer_phone')
    inlines = [OrderLineInline]
    readonly_fields = ('invoice_number', 'created_at', 'updated_at')
