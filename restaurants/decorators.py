from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def owner_required(view_func):
    """
    Stacks with @login_required semantics (redirects anonymous users to
    login) but additionally requires the logged-in user's profile to have
    the Owner role. A logged-in Cashier gets a 403, not a login redirect —
    they ARE authenticated, they just lack permission.
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if not profile or not profile.is_owner:
            raise PermissionDenied('Only the Owner role can access this page.')
        return view_func(request, *args, **kwargs)
    return _wrapped


def plan_required(feature_flag):
    """
    Gates a view behind a Plan boolean flag (e.g. 'has_inventory'). Stacks
    with @login_required — an authenticated user whose restaurant's plan
    doesn't include the feature gets a clear 403, not a silent redirect.

    Usage:
        @plan_required('has_inventory')
        def inventory_screen(request): ...

    Combine with @owner_required by stacking both decorators on the view;
    order doesn't matter for correctness here since both just check
    request.user/request.restaurant, which TenantMiddleware already set.
    """
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.restaurant or not request.restaurant.has_feature(feature_flag):
                raise PermissionDenied(
                    "Your plan doesn't include this feature. Contact your administrator to upgrade."
                )
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
