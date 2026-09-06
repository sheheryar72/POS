class TenantMiddleware:
    """
    Resolves the current request's tenant once, from the logged-in user's
    profile, and stashes it as request.restaurant. Every view scopes its
    queries through this instead of a global "the one restaurant" lookup —
    that's the whole difference between single-tenant and multi-tenant here.

    Anonymous requests (not logged in yet, e.g. the login page itself) get
    request.restaurant = None; views that need it are already behind
    @login_required / @owner_required, which run after this middleware and
    would reject the request before any tenant-scoped code executes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.restaurant = None
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            if profile:
                request.restaurant = profile.restaurant
        return self.get_response(request)
