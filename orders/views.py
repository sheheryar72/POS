import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from django.db.models import Sum, F

from menu.models import Category, ItemVariant, StockMovement
from restaurants.decorators import owner_required, plan_required

from .models import Order, OrderLine


class PosLoginView(LoginView):
    template_name = 'orders/login.html'


@login_required
def pos_screen(request):
    return render(request, 'orders/pos.html', {'restaurant': request.restaurant})


@login_required
def kitchen_screen(request):
    return render(request, 'orders/kitchen.html', {'restaurant': request.restaurant})


@login_required
def orders_history_screen(request):
    return render(request, 'orders/history.html', {'restaurant': request.restaurant})


@owner_required
def dashboard_screen(request):
    return render(request, 'orders/dashboard.html', {'restaurant': request.restaurant})


@login_required
@require_GET
def api_menu(request):
    categories = (
        Category.objects.filter(restaurant=request.restaurant, is_active=True)
        .prefetch_related('items__variants')
    )
    data = []
    for cat in categories:
        items = []
        for item in cat.items.filter(is_available=True):
            variants = [
                {
                    'id': v.id,
                    'name': v.name,
                    'price': str(v.price),
                    # Out-of-stock variants are still sent (shown, disabled
                    # in the UI) rather than filtered out here — a cashier
                    # should see an item exists but is temporarily out,
                    # not have it silently vanish from the menu.
                    'track_stock': v.track_stock,
                    'is_out_of_stock': v.is_out_of_stock,
                }
                for v in item.variants.filter(is_available=True)
            ]
            if not variants:
                continue
            items.append({
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'image_url': item.image.url if item.image else '',
                'variants': variants,
            })
        if items:
            data.append({'id': cat.id, 'name': cat.name, 'items': items})
    return JsonResponse({'categories': data})


def _serialize_order(order):
    return {
        'id': order.id,
        'invoice_number': order.invoice_number,
        'client_transaction_id': order.client_transaction_id,
        'order_type': order.order_type,
        'order_type_display': order.get_order_type_display(),
        'customer_name': order.customer_name,
        'customer_phone': order.customer_phone,
        'delivery_address': order.delivery_address,
        'status': order.status,
        'status_display': order.get_status_display(),
        'payment_method': order.payment_method,
        'discount_type': order.discount_type,
        'discount_value': str(order.discount_value),
        'tax_percent': str(order.tax_percent),
        'subtotal': str(order.subtotal),
        'discount_amount': str(order.discount_amount),
        'tax_amount': str(order.tax_amount),
        'total': str(order.total),
        'created_at': timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M'),
        'lines': [
            {
                'item_name': line.item_name,
                'variant_name': line.variant_name,
                'unit_price': str(line.unit_price),
                'quantity': line.quantity,
                'line_total': str(line.line_total),
                'note': line.note,
            }
            for line in order.lines.all()
        ],
    }


@login_required
@require_POST
def api_place_order(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    order, error, status_code = _create_order_from_payload(payload, request.restaurant, request.user)
    if error:
        return JsonResponse({'error': error}, status=status_code)

    return JsonResponse({'order': _serialize_order(order)}, status=201)


def _create_order_from_payload(payload, restaurant, user):
    """
    Validates payload and creates an Order + OrderLines for the given
    tenant (restaurant). Every dollar amount (subtotal/discount/tax/total)
    is derived server-side from OrderLine rows at read time (see Order
    properties) — the client never sends and can never dictate a total; it
    only chooses variant_ids, quantities, and a discount selection.

    Idempotent on client_transaction_id when provided: a retried/duplicated
    submission (e.g. an offline order re-sent after a dropped sync response)
    returns the existing order instead of creating a second one. The
    idempotency lookup is scoped to this restaurant too, since
    client_transaction_id is only unique per-device, and — while globally
    unique in practice given the device-id-embedded format — a cross-tenant
    match should never be trusted even if it somehow occurred.

    Returns (order, error_message, http_status). On success error_message is None.
    """
    client_transaction_id = (payload.get('client_transaction_id') or '').strip()[:64] or None

    if client_transaction_id:
        existing = Order.objects.filter(
            restaurant=restaurant, client_transaction_id=client_transaction_id
        ).first()
        if existing:
            return existing, None, 200

    items = payload.get('items') or []
    if not items:
        return None, 'Cart is empty.', 400

    order_type = payload.get('order_type', Order.OrderType.DINE_IN)
    if order_type not in Order.OrderType.values:
        return None, 'Invalid order type.', 400

    discount_type = payload.get('discount_type', Order.DiscountType.NONE)
    if discount_type not in Order.DiscountType.values:
        return None, 'Invalid discount type.', 400

    try:
        discount_value = Decimal(str(payload.get('discount_value') or '0'))
        if discount_value < 0:
            raise InvalidOperation
    except InvalidOperation:
        return None, 'Invalid discount value.', 400

    payment_method = 'cash'

    variant_ids = [entry.get('variant_id') for entry in items]
    # Scoped to this tenant's own categories — a variant_id belonging to
    # another restaurant must be rejected exactly like one that doesn't
    # exist at all, not silently sold.
    variants = ItemVariant.objects.filter(
        id__in=variant_ids, item__category__restaurant=restaurant
    ).select_related('item')
    variant_map = {v.id: v for v in variants}

    lines_to_create = []
    for entry in items:
        variant = variant_map.get(entry.get('variant_id'))
        if variant is None:
            return None, 'One of the selected items is no longer available.', 400
        try:
            quantity = int(entry.get('quantity', 1))
        except (TypeError, ValueError):
            quantity = 0
        if quantity < 1:
            return None, 'Quantity must be at least 1.', 400

        lines_to_create.append(OrderLine(
            variant=variant,
            item_name=variant.item.name,
            variant_name=variant.name,
            unit_price=variant.price,
            quantity=quantity,
            note=(entry.get('note') or '')[:255],
        ))

    try:
        with transaction.atomic():
            invoice_num = restaurant.reserve_invoice_number()
            order = Order.objects.create(
                restaurant=restaurant,
                invoice_number=f'{restaurant.invoice_prefix}-{invoice_num:05d}',
                client_transaction_id=client_transaction_id,
                order_type=order_type,
                customer_name=(payload.get('customer_name') or '')[:100],
                customer_phone=(payload.get('customer_phone') or '')[:30],
                delivery_address=(payload.get('delivery_address') or '')[:255],
                discount_type=discount_type,
                discount_value=discount_value,
                tax_percent=restaurant.tax_percent,
                payment_method=payment_method,
                created_by=user,
            )
            for line in lines_to_create:
                line.order = order
            OrderLine.objects.bulk_create(lines_to_create)

            # Deduct stock for every tracked variant sold. Never blocks the
            # sale on insufficient stock — offline orders can't check live
            # stock before completing, so the same rule applies uniformly
            # online: the sale always goes through, and going negative is
            # surfaced via the Inventory screen for the owner to reconcile,
            # not prevented here.
            for line in lines_to_create:
                if line.variant and line.variant.track_stock:
                    line.variant.record_movement(
                        movement_type='sale',
                        quantity_change=-line.quantity,
                        order_line=line,
                        user=user,
                    )
    except IntegrityError:
        # Lost a race against a concurrent sync retry with the same
        # client_transaction_id — the other request already created it.
        existing = Order.objects.filter(
            restaurant=restaurant, client_transaction_id=client_transaction_id
        ).first()
        if existing:
            return existing, None, 200
        raise

    return order, None, 201


@login_required
@require_POST
def api_sync_order(request):
    """
    Offline-sync endpoint: same validation/creation as api_place_order, but
    requires client_transaction_id and always reports whether this call
    created the order or found it already synced.
    """
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    client_transaction_id = (payload.get('client_transaction_id') or '').strip()
    if not client_transaction_id:
        return JsonResponse({'error': 'client_transaction_id is required for sync.'}, status=400)

    already_existed = Order.objects.filter(
        restaurant=request.restaurant, client_transaction_id=client_transaction_id
    ).exists()

    order, error, status_code = _create_order_from_payload(payload, request.restaurant, request.user)
    if error:
        return JsonResponse({
            'client_transaction_id': client_transaction_id,
            'status': 'error',
            'error': error,
        }, status=status_code)

    return JsonResponse({
        'client_transaction_id': client_transaction_id,
        'server_id': order.id,
        'invoice_number': order.invoice_number,
        'status': 'already_synced' if already_existed else 'synced',
        'order': _serialize_order(order),
    }, status=200 if already_existed else 201)


@login_required
@require_GET
def api_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('lines'), id=order_id, restaurant=request.restaurant
    )
    return JsonResponse({'order': _serialize_order(order)})


@login_required
@require_GET
def api_orders_queue(request):
    """Active orders for the kitchen view."""
    orders = Order.objects.filter(
        restaurant=request.restaurant,
        status__in=[Order.Status.PENDING, Order.Status.IN_PROGRESS],
    ).prefetch_related('lines')
    return JsonResponse({'orders': [_serialize_order(o) for o in orders]})


@login_required
@require_GET
def api_orders_history(request):
    orders = Order.objects.filter(restaurant=request.restaurant).prefetch_related('lines')

    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)

    date_str = request.GET.get('date')
    if date_str:
        orders = orders.filter(created_at__date=date_str)
    else:
        orders = orders.filter(created_at__date=timezone.localdate())

    orders = orders[:200]
    return JsonResponse({'orders': [_serialize_order(o) for o in orders]})


@login_required
@require_POST
def api_update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id, restaurant=request.restaurant)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    new_status = payload.get('status')
    if new_status not in Order.Status.values:
        return JsonResponse({'error': 'Invalid status.'}, status=400)

    order.status = new_status
    order.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'order': _serialize_order(order)})


@owner_required
@require_GET
def api_dashboard_summary(request):
    today = timezone.localdate()
    orders = Order.objects.filter(
        restaurant=request.restaurant, created_at__date=today
    ).exclude(status=Order.Status.CANCELLED)

    total_orders = orders.count()
    total_revenue = sum((o.total for o in orders), Decimal('0.00'))
    pending_count = orders.filter(status=Order.Status.PENDING).count()
    in_progress_count = orders.filter(status=Order.Status.IN_PROGRESS).count()
    completed_count = orders.filter(status=Order.Status.COMPLETED).count()

    return JsonResponse({
        'date': str(today),
        'total_orders': total_orders,
        'total_revenue': str(total_revenue),
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
    })


# ---------------------------------------------------------------------------
# Reports: Sales Summary, Top-Selling Items, Stock Report (Premium only)
# ---------------------------------------------------------------------------

def _parse_report_date_range(request):
    """
    Shared by every report endpoint: reads ?start=YYYY-MM-DD&end=YYYY-MM-DD,
    defaulting to the last 7 days (inclusive) when omitted. Returns
    (start_date, end_date) as date objects, or None (with the error
    JsonResponse already built) if the input is invalid.
    """
    today = timezone.localdate()
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')

    try:
        start = timezone.datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else today - timezone.timedelta(days=6)
        end = timezone.datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else today
    except ValueError:
        return None, JsonResponse({'error': 'Dates must be in YYYY-MM-DD format.'}, status=400)

    if start > end:
        return None, JsonResponse({'error': '"start" must not be after "end".'}, status=400)

    return (start, end), None


@owner_required
@plan_required('has_reports')
def reports_screen(request):
    return render(request, 'orders/reports.html', {'restaurant': request.restaurant})


@owner_required
@plan_required('has_reports')
@require_GET
def api_reports_sales_summary(request):
    date_range, error = _parse_report_date_range(request)
    if error:
        return error
    start, end = date_range

    orders = Order.objects.filter(
        restaurant=request.restaurant, created_at__date__gte=start, created_at__date__lte=end,
    ).exclude(status=Order.Status.CANCELLED).prefetch_related('lines')

    total_orders = orders.count()
    total_revenue = sum((o.total for o in orders), Decimal('0.00'))
    average_order_value = (total_revenue / total_orders).quantize(Decimal('0.01')) if total_orders else Decimal('0.00')

    by_day = {}
    for order in orders:
        day = str(timezone.localtime(order.created_at).date())
        bucket = by_day.setdefault(day, {'date': day, 'orders': 0, 'revenue': Decimal('0.00')})
        bucket['orders'] += 1
        bucket['revenue'] += order.total

    daily = [
        {'date': row['date'], 'orders': row['orders'], 'revenue': str(row['revenue'])}
        for row in sorted(by_day.values(), key=lambda r: r['date'])
    ]

    return JsonResponse({
        'start': str(start),
        'end': str(end),
        'total_orders': total_orders,
        'total_revenue': str(total_revenue),
        'average_order_value': str(average_order_value),
        'daily': daily,
    })


@owner_required
@plan_required('has_reports')
@require_GET
def api_reports_top_items(request):
    date_range, error = _parse_report_date_range(request)
    if error:
        return error
    start, end = date_range

    lines = (
        OrderLine.objects.filter(
            order__restaurant=request.restaurant,
            order__created_at__date__gte=start,
            order__created_at__date__lte=end,
        )
        .exclude(order__status=Order.Status.CANCELLED)
        .values('item_name', 'variant_name')
        .annotate(
            quantity_sold=Sum('quantity'),
            revenue=Sum(F('unit_price') * F('quantity')),
        )
        .order_by('-revenue')[:20]
    )

    items = [
        {
            'item_name': row['item_name'],
            'variant_name': row['variant_name'],
            'quantity_sold': row['quantity_sold'],
            'revenue': str(row['revenue']),
        }
        for row in lines
    ]

    return JsonResponse({'start': str(start), 'end': str(end), 'items': items})


@owner_required
@plan_required('has_reports')
@require_GET
def api_reports_stock(request):
    """
    Current stock snapshot (not date-ranged — "as of now") plus stock
    movement totals over the requested date range, split by movement type.
    Only meaningful for tenants with Inventory, but Reports and Inventory
    are both Premium-only today so this is never reachable without it.
    """
    date_range, error = _parse_report_date_range(request)
    if error:
        return error
    start, end = date_range

    variants = ItemVariant.objects.filter(
        track_stock=True, item__category__restaurant=request.restaurant
    ).select_related('item', 'item__category')

    tracked_count = variants.count()
    out_of_stock_count = sum(1 for v in variants if v.is_out_of_stock)
    low_stock_count = sum(1 for v in variants if v.is_low_stock)
    total_units_in_stock = sum(v.stock_quantity for v in variants)

    movements = StockMovement.objects.filter(
        variant__item__category__restaurant=request.restaurant,
        created_at__date__gte=start,
        created_at__date__lte=end,
    ).values('movement_type').annotate(total_change=Sum('quantity_change'))

    movement_totals = {row['movement_type']: row['total_change'] for row in movements}

    return JsonResponse({
        'start': str(start),
        'end': str(end),
        'tracked_count': tracked_count,
        'out_of_stock_count': out_of_stock_count,
        'low_stock_count': low_stock_count,
        'total_units_in_stock': total_units_in_stock,
        'movement_totals': {
            'sale': movement_totals.get(StockMovement.MovementType.SALE, 0),
            'purchase': movement_totals.get(StockMovement.MovementType.PURCHASE, 0),
            'adjustment': movement_totals.get(StockMovement.MovementType.ADJUSTMENT, 0),
        },
    })
