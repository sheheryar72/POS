from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class JWTUserMiddleware:
    """
    Lets the mobile app authenticate with `Authorization: Bearer <token>`
    against the exact same views the web POS already uses (api_menu,
    api_place_order, etc.) — no view code duplicated or changed.

    Runs after AuthenticationMiddleware, before TenantMiddleware. If a
    Bearer token is present and valid, it overrides request.user (normally
    AnonymousUser for a cookieless mobile request) so every downstream
    @login_required / @owner_required / request.restaurant check just
    works, unmodified. No Authorization header -> falls through to
    whatever AuthenticationMiddleware already set (session auth), so the
    web app's behavior is completely unaffected.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()

    def __call__(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            try:
                result = self.jwt_auth.authenticate(request)
            except (InvalidToken, TokenError):
                result = None
            if result is not None:
                request.user, _ = result
                # CSRF exists to stop a browser from being tricked into
                # replaying a session COOKIE it already holds — it has
                # nothing to protect here: a Bearer token is sent
                # explicitly by the mobile app itself, never attached
                # automatically the way a cookie is, so there's no
                # forged-request risk to guard against. Django's
                # CsrfViewMiddleware (which runs later) honors this same
                # flag for session-authenticated requests that opt out
                # (e.g. DRF's SessionAuthentication.enforce_csrf).
                request._dont_enforce_csrf_checks = True
        return self.get_response(request)


class ApiJsonErrorMiddleware:
    """
    The web POS's @login_required/@owner_required/@plan_required decorators
    are fine returning an HTML redirect or Django's HTML 403 page — a
    browser handles those. A mobile JSON client can't, so for any request
    under /api/ we translate the same underlying conditions into JSON
    instead of changing the decorators (which must keep working for the
    browser-facing screens too).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not request.path.startswith('/api/'):
            return response

        # @login_required redirects anonymous users with a 302 to /login/.
        # A mobile client should get a plain 401 instead of following it.
        if response.status_code == 302 and response.get('Location', '').startswith('/login/'):
            return JsonResponse({'error': 'Authentication required.'}, status=401)

        return response

    def process_exception(self, request, exception):
        if request.path.startswith('/api/') and isinstance(exception, PermissionDenied):
            return JsonResponse({'error': str(exception) or 'Permission denied.'}, status=403)
        return None
