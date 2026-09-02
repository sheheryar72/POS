from django.contrib import admin

from .models import Category, ItemVariant, MenuItem


class ItemVariantInline(admin.TabularInline):
    model = ItemVariant
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'is_active')
    list_editable = ('sort_order', 'is_active')


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_available', 'sort_order')
    list_editable = ('is_available', 'sort_order')
    list_filter = ('category', 'is_available')
    search_fields = ('name',)
    inlines = [ItemVariantInline]
