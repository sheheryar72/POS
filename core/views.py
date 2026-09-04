from django.contrib.staticfiles import finders
from django.http import HttpResponse, HttpResponseNotFound


def service_worker(request):
    """
    Serves static/js/sw.js at the site root (not /static/js/sw.js) so its
    scope covers the whole app — a service worker can only control pages at
    or below the path it's served from. Goes through Django's staticfiles
    finders so this works the same way in dev (STATICFILES_DIRS) and in
    production (WhiteNoise-collected STATIC_ROOT) without special-casing.
    """
    path = finders.find('js/sw.js')
    if not path:
        return HttpResponseNotFound('Service worker not found.')
    with open(path, 'rb') as f:
        content = f.read()
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response
