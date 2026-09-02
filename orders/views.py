import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from menu.models import Category, ItemVariant
from restaurants.models import Restaurant

from .models import Order, OrderLine


class PosLoginView(LoginView):
    template_name = 'orders/login.html'


@login_required
def pos_screen(request):
    restaurant = Restaurant.get_current()
    return render(request, 'orders/pos.html', {'restaurant': restaurant})


@login_required
def kitchen_screen(request):
    restaurant = Restaurant.get_current()
    return render(request, 'orders/kitchen.html', {'restaurant': restaurant})


@login_required
def orders_history_screen(request):
    restaurant = Restaurant.get_current()
    return render(request, 'orders/history.html', {'restaurant': restaurant})


@login_required
def dashboard_screen(request):
    restaurant = Restaurant.get_current()
    return render(request, 'orders/dashboard.html', {'restaurant': restaurant})


@login_required
@require_GET
def api_menu(request):
    categories = Category.objects.filter(is_active=True).prefetch_related('items__variants')
    data = []
    for cat in categories:
        items = []
        for item in cat.items.filter(is_available=True):
            variants = [
                {'id': v.id, 'name': v.name, 'price': str(v.price)}
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

    items = payload.get('items') or []
    if not items:
        return JsonResponse({'error': 'Cart is empty.'}, status=400)

    order_type = payload.get('order_type', Order.OrderType.DINE_IN)
    if order_type not in Order.OrderType.values:
        return JsonResponse({'error': 'Invalid order type.'}, status=400)

    discount_type = payload.get('discount_type', Order.DiscountType.NONE)
    if discount_type not in Order.DiscountType.values:
        return JsonResponse({'error': 'Invalid discount type.'}, status=400)

    try:
        discount_value = Decimal(str(payload.get('discount_value') or '0'))
        if discount_value < 0:
            raise InvalidOperation
    except InvalidOperation:
        return JsonResponse({'error': 'Invalid discount value.'}, status=400)

    payment_method = 'cash'

    restaurant = Restaurant.get_current()

    variant_ids = [entry.get('variant_id') for entry in items]
    variants = ItemVariant.objects.filter(id__in=variant_ids).select_related('item')
    variant_map = {v.id: v for v in variants}

    lines_to_create = []
    for entry in items:
        variant = variant_map.get(entry.get('variant_id'))
        if variant is None:
            return JsonResponse({'error': 'One of the selected items is no longer available.'}, status=400)
        try:
            quantity = int(entry.get('quantity', 1))
        except (TypeError, ValueError):
            quantity = 0
        if quantity < 1:
            return JsonResponse({'error': 'Quantity must be at least 1.'}, status=400)

        lines_to_create.append(OrderLine(
            variant=variant,
            item_name=variant.item.name,
            variant_name=variant.name,
            unit_price=variant.price,
            quantity=quantity,
            note=(entry.get('note') or '')[:255],
        ))

    with transaction.atomic():
        invoice_num = restaurant.reserve_invoice_number()
        order = Order.objects.create(
            restaurant=restaurant,
            invoice_number=f'{restaurant.invoice_prefix}-{invoice_num:05d}',
            order_type=order_type,
            customer_name=(payload.get('customer_name') or '')[:100],
            customer_phone=(payload.get('customer_phone') or '')[:30],
            delivery_address=(payload.get('delivery_address') or '')[:255],
            discount_type=discount_type,
            discount_value=discount_value,
            tax_percent=restaurant.tax_percent,
            payment_method=payment_method,
            created_by=request.user,
        )
        for line in lines_to_create:
            line.order = order
        OrderLine.objects.bulk_create(lines_to_create)

    return JsonResponse({'order': _serialize_order(order)}, status=201)


@login_required
@require_GET
def api_order_detail(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related('lines'), id=order_id)
    return JsonResponse({'order': _serialize_order(order)})


@login_required
@require_GET
def api_orders_queue(request):
    """Active orders for the kitchen view."""
    orders = Order.objects.filter(
        status__in=[Order.Status.PENDING, Order.Status.IN_PROGRESS]
    ).prefetch_related('lines')
    return JsonResponse({'orders': [_serialize_order(o) for o in orders]})


@login_required
@require_GET
def api_orders_history(request):
    orders = Order.objects.prefetch_related('lines')

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
    order = get_object_or_404(Order, id=order_id)
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


@login_required
@require_GET
def api_dashboard_summary(request):
    today = timezone.localdate()
    orders = Order.objects.filter(created_at__date=today).exclude(status=Order.Status.CANCELLED)

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
