from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Plan, Restaurant, UserProfile

User = get_user_model()


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """
    Fully admin-managed pricing tiers — add/edit a plan and flip its feature
    flags here, no code changes needed. Restaurants → Plans → Add Plan.
    """
    list_display = ('name', 'price', 'has_inventory', 'has_reports', 'is_active', 'restaurant_count', 'sort_order')
    list_editable = ('sort_order', 'is_active')

    def restaurant_count(self, obj):
        return obj.restaurants.count()
    restaurant_count.short_description = 'Tenants on this plan'


class StaffInline(admin.TabularInline):
    """Shown on the Restaurant admin page — quick view of who belongs to this tenant."""
    model = UserProfile
    extra = 0
    fields = ('user', 'role', 'created_at')
    readonly_fields = ('created_at',)
    can_delete = False
    verbose_name = 'Staff member'
    verbose_name_plural = 'Staff'


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    """
    Step 1 of onboarding a new client: Admin → Restaurants → Add Restaurant
    (pick their Plan here). Step 2 (creating their Owner login) happens on
    the User admin page below, via the Profile inline — see UserProfileInline.
    """
    list_display = ('name', 'plan', 'currency_symbol', 'tax_percent', 'phone', 'staff_count', 'created_at')
    list_filter = ('plan',)
    search_fields = ('name', 'phone')
    inlines = [StaffInline]

    def staff_count(self, obj):
        return obj.staff.count()
    staff_count.short_description = 'Staff'


class UserProfileInline(admin.StackedInline):
    """
    Step 2 of onboarding: after creating a new User below (Django's normal
    "Add user" flow — username + password, properly hashed), this inline is
    where you pick which Restaurant they belong to and their Role. A user
    saved without a profile can't log into the POS at all (TenantMiddleware
    has nothing to resolve), so this is the one required extra step.
    """
    model = UserProfile
    can_delete = False
    verbose_name = 'POS Profile (restaurant + role)'
    verbose_name_plural = 'POS Profile (restaurant + role)'
    min_num = 0
    max_num = 1


class UserAdmin(DjangoUserAdmin):
    inlines = (UserProfileInline,)
    list_display = DjangoUserAdmin.list_display + ('restaurant_name', 'role')
    list_select_related = ('profile', 'profile__restaurant')

    def restaurant_name(self, obj):
        return obj.profile.restaurant.name if hasattr(obj, 'profile') else '—'
    restaurant_name.short_description = 'Restaurant'

    def role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, 'profile') else '—'
    role.short_description = 'Role'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
