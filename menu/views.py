import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from restaurants.decorators import owner_required, plan_required

from .models import Category, ItemVariant, MenuItem, StockMovement


@owner_required
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
                'track_stock': v.track_stock,
                'stock_quantity': v.stock_quantity,
                'low_stock_threshold': v.low_stock_threshold,
                'is_out_of_stock': v.is_out_of_stock,
                'is_low_stock': v.is_low_stock,
            }
            for v in item.variants.all().order_by('sort_order', 'price')
        ],
    }


@owner_required
def api_manage_categories(request):
    if request.method == 'GET':
        categories = Category.objects.filter(restaurant=request.restaurant).order_by('sort_order', 'name')
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
            restaurant=request.restaurant,
            name=name[:100],
            sort_order=int(payload.get('sort_order') or 0),
        )
        return JsonResponse({'id': category.id, 'name': category.name}, status=201)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@owner_required
@require_http_methods(['POST', 'DELETE'])
def api_manage_category_detail(request, category_id):
    category = get_object_or_404(Category, id=category_id, restaurant=request.restaurant)

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


@owner_required
def api_manage_items(request):
    if request.method == 'GET':
        items = (
            MenuItem.objects.filter(category__restaurant=request.restaurant)
            .select_related('category')
            .prefetch_related('variants')
        )
        category_id = request.GET.get('category_id')
        if category_id:
            items = items.filter(category_id=category_id)
        return JsonResponse({'items': [_serialize_item(i) for i in items]})

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        category_id = request.POST.get('category_id')
        if not name:
            return JsonResponse({'error': 'Item name is required.'}, status=400)
        category = get_object_or_404(Category, id=category_id, restaurant=request.restaurant)

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

            track_stock = bool(v.get('track_stock'))
            try:
                low_stock_threshold = int(v.get('low_stock_threshold') or 0)
                initial_stock = int(v.get('stock_quantity') or 0) if track_stock else 0
            except (TypeError, ValueError):
                item.delete()
                return JsonResponse({'error': f'Invalid stock values for variant "{v_name}".'}, status=400)

            variant = ItemVariant.objects.create(
                item=item, name=v_name, price=price, sort_order=idx,
                track_stock=track_stock, low_stock_threshold=max(low_stock_threshold, 0),
            )
            if track_stock and initial_stock:
                variant.record_movement(
                    movement_type=StockMovement.MovementType.PURCHASE,
                    quantity_change=initial_stock,
                    note='Opening stock (item created)',
                    user=request.user,
                )

        return JsonResponse({'item': _serialize_item(item)}, status=201)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@owner_required
@require_http_methods(['POST', 'DELETE'])
def api_manage_item_detail(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, category__restaurant=request.restaurant)

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
        item.category = get_object_or_404(
            Category, id=request.POST.get('category_id'), restaurant=request.restaurant
        )
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

            try:
                low_stock_threshold = max(int(v.get('low_stock_threshold') or 0), 0)
            except (TypeError, ValueError):
                return JsonResponse({'error': f'Invalid low stock threshold for variant "{v_name}".'}, status=400)
            track_stock = bool(v.get('track_stock'))

            v_id = v.get('id')
            if v_id:
                variant = item.variants.filter(id=v_id).first()
                if variant:
                    variant.name = v_name
                    variant.price = price
                    variant.sort_order = idx
                    variant.is_available = v.get('is_available', True)
                    # track_stock/low_stock_threshold are plain settings —
                    # editable here like any other field. stock_quantity is
                    # deliberately NOT accepted from this endpoint at all;
                    # it only ever changes via ItemVariant.record_movement()
                    # (Stock Adjustment screen or a sale), so the ledger in
                    # StockMovement can never drift from the cached count.
                    variant.track_stock = track_stock
                    variant.low_stock_threshold = low_stock_threshold
                    variant.save()
                    kept_ids.append(variant.id)
                    continue

            variant = ItemVariant.objects.create(
                item=item, name=v_name, price=price, sort_order=idx,
                track_stock=track_stock, low_stock_threshold=low_stock_threshold,
            )
            if track_stock:
                try:
                    initial_stock = int(v.get('stock_quantity') or 0)
                except (TypeError, ValueError):
                    initial_stock = 0
                if initial_stock:
                    variant.record_movement(
                        movement_type=StockMovement.MovementType.PURCHASE,
                        quantity_change=initial_stock,
                        note='Opening stock (variant added)',
                        user=request.user,
                    )
            kept_ids.append(variant.id)

        item.variants.exclude(id__in=kept_ids).delete()

    return JsonResponse({'item': _serialize_item(item)})


# ---------------------------------------------------------------------------
# Inventory: Stock Overview, Stock Adjustment, Stock History
# ---------------------------------------------------------------------------

@owner_required
@plan_required('has_inventory')
def inventory_screen(request):
    return render(request, 'menu/inventory.html')


def _serialize_variant_stock(variant):
    return {
        'id': variant.id,
        'item_id': variant.item_id,
        'item_name': variant.item.name,
        'variant_name': variant.name,
        'category_name': variant.item.category.name,
        'stock_quantity': variant.stock_quantity,
        'low_stock_threshold': variant.low_stock_threshold,
        'is_out_of_stock': variant.is_out_of_stock,
        'is_low_stock': variant.is_low_stock,
    }


@owner_required
@plan_required('has_inventory')
def api_inventory_overview(request):
    """
    All tracked variants for this tenant, split into out-of-stock /
    low-stock / ok, for the Inventory screen's summary panels. A single
    small restaurant or shop won't have enough tracked variants for this to
    need pagination.
    """
    variants = (
        ItemVariant.objects.filter(track_stock=True, item__category__restaurant=request.restaurant)
        .select_related('item', 'item__category')
        .order_by('item__category__sort_order', 'item__name', 'sort_order')
    )

    out_of_stock, low_stock, ok = [], [], []
    for v in variants:
        row = _serialize_variant_stock(v)
        if v.is_out_of_stock:
            out_of_stock.append(row)
        elif v.is_low_stock:
            low_stock.append(row)
        else:
            ok.append(row)

    return JsonResponse({
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'ok': ok,
        'tracked_count': len(out_of_stock) + len(low_stock) + len(ok),
    })


@owner_required
@plan_required('has_inventory')
def api_inventory_variants(request):
    """All tracked variants for this tenant (for the Stock Adjustment screen's picker)."""
    variants = (
        ItemVariant.objects.filter(track_stock=True, item__category__restaurant=request.restaurant)
        .select_related('item', 'item__category')
        .order_by('item__category__sort_order', 'item__name', 'sort_order')
    )
    return JsonResponse({'variants': [_serialize_variant_stock(v) for v in variants]})


@owner_required
@plan_required('has_inventory')
@require_http_methods(['POST'])
def api_inventory_adjust(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    variant_id = payload.get('variant_id')
    movement_type = payload.get('movement_type')
    note = (payload.get('note') or '').strip()

    if movement_type not in (StockMovement.MovementType.PURCHASE, StockMovement.MovementType.ADJUSTMENT):
        return JsonResponse({'error': 'Invalid movement type.'}, status=400)

    variant = ItemVariant.objects.filter(
        id=variant_id, track_stock=True, item__category__restaurant=request.restaurant
    ).select_related('item').first()
    if not variant:
        return JsonResponse({'error': 'That item is not stock-tracked or does not exist.'}, status=400)

    try:
        quantity = int(payload.get('quantity'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Quantity must be a whole number.'}, status=400)

    if movement_type == StockMovement.MovementType.PURCHASE:
        if quantity <= 0:
            return JsonResponse({'error': 'Purchase quantity must be positive.'}, status=400)
        quantity_change = quantity
    else:
        # Adjustment: quantity is the signed delta directly (can be
        # negative, e.g. correcting for spoilage/theft/miscount).
        if quantity == 0:
            return JsonResponse({'error': 'Adjustment quantity cannot be zero.'}, status=400)
        quantity_change = quantity

    movement = variant.record_movement(
        movement_type=movement_type,
        quantity_change=quantity_change,
        note=note[:255],
        user=request.user,
    )

    return JsonResponse({
        'variant': _serialize_variant_stock(variant),
        'movement': {
            'id': movement.id,
            'quantity_change': movement.quantity_change,
            'resulting_quantity': movement.resulting_quantity,
        },
    }, status=201)


@owner_required
@plan_required('has_inventory')
def api_inventory_history(request):
    movements = (
        StockMovement.objects.filter(variant__item__category__restaurant=request.restaurant)
        .select_related('variant', 'variant__item', 'created_by')
    )

    variant_id = request.GET.get('variant_id')
    if variant_id:
        movements = movements.filter(variant_id=variant_id)

    movement_type = request.GET.get('movement_type')
    if movement_type:
        movements = movements.filter(movement_type=movement_type)

    date_str = request.GET.get('date')
    if date_str:
        movements = movements.filter(created_at__date=date_str)

    movements = movements[:300]

    data = [
        {
            'id': m.id,
            'item_name': m.variant.item.name,
            'variant_name': m.variant.name,
            'movement_type': m.movement_type,
            'movement_type_display': m.get_movement_type_display(),
            'quantity_change': m.quantity_change,
            'resulting_quantity': m.resulting_quantity,
            'note': m.note,
            'created_by': m.created_by.username if m.created_by else '',
            'created_at': timezone.localtime(m.created_at).strftime('%Y-%m-%d %H:%M'),
        }
        for m in movements
    ]
    return JsonResponse({'movements': data})
