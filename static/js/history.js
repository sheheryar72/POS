$(function () {
    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    var today = new Date().toISOString().slice(0, 10);
    $('#filter-date').val(today);

    function loadHistory() {
        if (!navigator.onLine) {
            return loadLocalOnly();
        }

        var params = {};
        var date = $('#filter-date').val();
        var status = $('#filter-status').val();
        if (date) params.date = date;
        if (status) params.status = status;

        ajax({ url: '/api/orders/history/', method: 'GET', data: params }).done(function (res) {
            $('#history-offline-note').hide();
            mergeWithLocalPending(res.orders, date);
        }).fail(function () {
            loadLocalOnly();
        });
    }

    function loadLocalOnly() {
        $('#history-offline-note').show();
        mergeWithLocalPending([], $('#filter-date').val());
    }

    // Orders still sitting in the local sync queue don't exist on the server
    // yet, so /api/orders/history/ can never return them — merge them in
    // here so a cashier reviewing "today's orders" while offline (or right
    // after coming back online, before the sync engine has caught up) can
    // still see everything that's actually happened on this device today.
    function mergeWithLocalPending(serverOrders, dateFilter) {
        posDb.getAllOrders().then(function (localOrders) {
            var pending = localOrders.filter(function (o) {
                if (o.status !== 'PENDING_SYNC' && o.status !== 'FAILED') return false;
                if (!dateFilter) return true;
                return (o.created_at || '').slice(0, 10) === dateFilter;
            });
            renderTable(pending.concat(serverOrders));
        }).catch(function () {
            renderTable(serverOrders);
        });
    }

    function renderTable(orders) {
        var $body = $('#history-body').empty();
        if (!orders.length) {
            $body.append('<tr><td colspan="6" style="color:#888">No orders found.</td></tr>');
            return;
        }
        orders.forEach(function (order) {
            var isPendingSync = !!order.is_offline;
            var $row = $('<tr></tr>');
            if (isPendingSync) $row.addClass('pending-sync-row');
            $row.append($('<td></td>').text(order.invoice_number));
            $row.append($('<td></td>').text(order.order_type_display));
            var $statusTd = $('<td></td>');
            var statusClass = isPendingSync ? 'pending_sync' : order.status;
            var statusLabel = isPendingSync ? 'Pending Sync' : order.status_display;
            $statusTd.append($('<span class="status-badge"></span>').addClass(statusClass).text(statusLabel));
            $row.append($statusTd);
            $row.append($('<td></td>').text(window.CURRENCY + order.total));
            $row.append($('<td></td>').text(order.created_at));
            var $actionTd = $('<td></td>');
            var $viewBtn = $('<button type="button" class="link-btn">View</button>').on('click', function () {
                showDetail(order);
            });
            $actionTd.append($viewBtn);
            $row.append($actionTd);
            $body.append($row);
        });
    }

    function showDetail(order) {
        var $content = $('#order-detail-content').empty();
        $content.append('<h3>' + order.invoice_number + '</h3>');
        $content.append('<div class="receipt-meta">' + order.order_type_display + ' — ' + order.created_at + '</div>');
        $content.append('<div class="receipt-divider"></div>');
        order.lines.forEach(function (line) {
            var $l = $('<div class="receipt-line"></div>');
            $l.append($('<span></span>').text(line.quantity + ' x ' + line.item_name + ' (' + line.variant_name + ')'));
            $l.append($('<span></span>').text(window.CURRENCY + line.line_total));
            $content.append($l);
        });
        $content.append('<div class="receipt-divider"></div>');
        $content.append(row('Subtotal', window.CURRENCY + order.subtotal));
        $content.append(row('Discount', window.CURRENCY + order.discount_amount));
        $content.append(row('Tax', window.CURRENCY + order.tax_amount));
        $content.append(row('Total', window.CURRENCY + order.total));
        $content.append(row('Payment', order.payment_method.toUpperCase()));
        $content.append(row('Status', order.is_offline ? 'Pending Sync' : order.status_display));
        $('#order-detail-modal').css('display', 'flex');
    }

    function row(label, value) {
        var $r = $('<div class="receipt-line"></div>');
        $r.append($('<span></span>').text(label));
        $r.append($('<span></span>').text(value));
        return $r;
    }

    $('#close-detail-btn').on('click', function () {
        $('#order-detail-modal').hide();
    });

    $('#filter-date, #filter-status').on('change', loadHistory);

    window.addEventListener('online', loadHistory);
    window.addEventListener('offline', loadHistory);
    if (window.posSync) {
        posSync.onSyncEvent(function (event) {
            if (event === 'order_synced' || event === 'sync_complete') loadHistory();
        });
    }

    loadHistory();
});
