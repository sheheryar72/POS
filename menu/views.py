import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .models import Category, ItemVariant, MenuItem


@login_required
def menu_manage_screen(request):
    return render(request, 'menu/manage.html')


def _serialize_item(item):
    return {
        'id': item.id,
        'name': item.name,
        'description': item.description,
        'category_id': item.category_id,
        'is_available': item.is_available,
        'sort_order': item.sort_order,
        'image_url': item.image.url if item.image else '',
        'variants': [
            {
                'id': v.id,
                'name': v.name,
                'price': str(v.price),
                'is_available': v.is_available,
                'sort_order': v.sort_order,
            }
            for v in item.variants.all().order_by('sort_order', 'price')
        ],
    }


@login_required
def api_manage_categories(request):
    if request.method == 'GET':
        categories = Category.objects.all().order_by('sort_order', 'name')
        data = [
            {
                'id': c.id,
                'name': c.name,
                'sort_order': c.sort_order,
                'is_active': c.is_active,
                'item_count': c.items.count(),
            }
            for c in categories
        ]
        return JsonResponse({'categories': data})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid request body.'}, status=400)
        name = (payload.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Category name is required.'}, status=400)
        category = Category.objects.create(
            name=name[:100],
            sort_order=int(payload.get('sort_order') or 0),
        )
        return JsonResponse({'id': category.id, 'name': category.name}, status=201)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@login_required
@require_http_methods(['POST', 'DELETE'])
def api_manage_category_detail(request, category_id):
    category = get_object_or_404(Category, id=category_id)

    if request.method == 'DELETE':
        category.delete()
        return JsonResponse({'ok': True})

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    name = payload.get('name')
    if name is not None:
        name = name.strip()
        if not name:
            return JsonResponse({'error': 'Category name cannot be empty.'}, status=400)
        category.name = name[:100]
    if 'is_active' in payload:
        category.is_active = bool(payload['is_active'])
    if 'sort_order' in payload:
        category.sort_order = int(payload.get('sort_order') or 0)
    category.save()
    return JsonResponse({'ok': True})


@login_required
def api_manage_items(request):
    if request.method == 'GET':
        items = MenuItem.objects.select_related('category').prefetch_related('variants')
        category_id = request.GET.get('category_id')
        if category_id:
            items = items.filter(category_id=category_id)
        return JsonResponse({'items': [_serialize_item(i) for i in items]})

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        category_id = request.POST.get('category_id')
        if not name:
            return JsonResponse({'error': 'Item name is required.'}, status=400)
        category = get_object_or_404(Category, id=category_id)

        variants_raw = request.POST.get('variants')
        try:
            variants = json.loads(variants_raw) if variants_raw else []
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid variants data.'}, status=400)
        if not variants:
            return JsonResponse({'error': 'At least one variant with a price is required.'}, status=400)

        item = MenuItem.objects.create(
            category=category,
            name=name[:150],
            description=(request.POST.get('description') or '')[:255],
            image=request.FILES.get('image'),
        )
        for idx, v in enumerate(variants):
            v_name = (v.get('name') or 'Regular').strip()[:50]
            try:
                price = float(v.get('price'))
                if price < 0:
                    raise ValueError
            except (TypeError, ValueError):
                item.delete()
                return JsonResponse({'error': f'Invalid price for variant "{v_name}".'}, status=400)
            ItemVariant.objects.create(item=item, name=v_name, price=price, sort_order=idx)

        return JsonResponse({'item': _serialize_item(item)}, status=201)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@login_required
@require_http_methods(['POST', 'DELETE'])
def api_manage_item_detail(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)

    if request.method == 'DELETE':
        item.delete()
        return JsonResponse({'ok': True})

    name = request.POST.get('name')
    if name is not None:
        name = name.strip()
        if not name:
            return JsonResponse({'error': 'Item name cannot be empty.'}, status=400)
        item.name = name[:150]
    if 'description' in request.POST:
        item.description = (request.POST.get('description') or '')[:255]
    if 'category_id' in request.POST:
        item.category = get_object_or_404(Category, id=request.POST.get('category_id'))
    if 'is_available' in request.POST:
        item.is_available = request.POST.get('is_available') in ('true', '1', 'True')
    if request.FILES.get('image'):
        item.image = request.FILES['image']
    item.save()

    variants_raw = request.POST.get('variants')
    if variants_raw:
        try:
            variants = json.loads(variants_raw)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid variants data.'}, status=400)

        kept_ids = []
        for idx, v in enumerate(variants):
            v_name = (v.get('name') or 'Regular').strip()[:50]
            try:
                price = float(v.get('price'))
                if price < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return JsonResponse({'error': f'Invalid price for variant "{v_name}".'}, status=400)

            v_id = v.get('id')
            if v_id:
                variant = item.variants.filter(id=v_id).first()
                if variant:
                    variant.name = v_name
                    variant.price = price
                    variant.sort_order = idx
                    variant.is_available = v.get('is_available', True)
                    variant.save()
                    kept_ids.append(variant.id)
                    continue
            variant = ItemVariant.objects.create(
                item=item, name=v_name, price=price, sort_order=idx
            )
            kept_ids.append(variant.id)

        item.variants.exclude(id__in=kept_ids).delete()

    return JsonResponse({'item': _serialize_item(item)})
