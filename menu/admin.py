from django.contrib import admin

from .models import Category, ItemVariant, MenuItem, StockMovement


class ItemVariantInline(admin.TabularInline):
    model = ItemVariant
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'sort_order', 'is_active')
    list_editable = ('sort_order', 'is_active')
    list_filter = ('restaurant', 'is_active')


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'restaurant_name', 'is_available', 'sort_order')
    list_editable = ('is_available', 'sort_order')
    list_filter = ('category__restaurant', 'category', 'is_available')
    search_fields = ('name',)
    inlines = [ItemVariantInline]
    list_select_related = ('category', 'category__restaurant')

    def restaurant_name(self, obj):
        return obj.category.restaurant.name
    restaurant_name.short_description = 'Restaurant'


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('variant', 'movement_type', 'quantity_change', 'resulting_quantity', 'created_by', 'created_at')
    list_filter = ('movement_type', 'created_at')
    search_fields = ('variant__name', 'variant__item__name', 'note')
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
