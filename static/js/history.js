$(function () {
    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    var today = new Date().toISOString().slice(0, 10);
    $('#filter-date').val(today);

    function loadHistory() {
        var params = {};
        var date = $('#filter-date').val();
        var status = $('#filter-status').val();
        if (date) params.date = date;
        if (status) params.status = status;

        ajax({ url: '/api/orders/history/', method: 'GET', data: params }).done(function (res) {
            renderTable(res.orders);
        });
    }

    function renderTable(orders) {
        var $body = $('#history-body').empty();
        if (!orders.length) {
            $body.append('<tr><td colspan="6" style="color:#888">No orders found.</td></tr>');
            return;
        }
        orders.forEach(function (order) {
            var $row = $('<tr></tr>');
            $row.append($('<td></td>').text(order.invoice_number));
            $row.append($('<td></td>').text(order.order_type_display));
            var $statusTd = $('<td></td>');
            $statusTd.append($('<span class="status-badge"></span>').addClass(order.status).text(order.status_display));
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
        $content.append(row('Status', order.status_display));
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

    loadHistory();
});
