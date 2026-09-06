def restaurant(request):
    """
    Makes {{ restaurant }} available in every template without each view
    needing to pass it explicitly — set once per request by TenantMiddleware
    as request.restaurant (None for anonymous/no-profile requests, e.g. the
    login page).
    """
    return {'restaurant': getattr(request, 'restaurant', None)}
