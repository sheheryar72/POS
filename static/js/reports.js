$(function () {
    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    function todayStr() {
        return new Date().toISOString().slice(0, 10);
    }

    function sevenDaysAgoStr() {
        var d = new Date();
        d.setDate(d.getDate() - 6);
        return d.toISOString().slice(0, 10);
    }

    $('#report-start-date').val(sevenDaysAgoStr());
    $('#report-end-date').val(todayStr());

    function currentRange() {
        return { start: $('#report-start-date').val(), end: $('#report-end-date').val() };
    }

    // ---------------- Tabs ----------------
    $('.inventory-tab').on('click', function () {
        var tab = $(this).data('tab');
        $('.inventory-tab').removeClass('active');
        $(this).addClass('active');
        $('.inventory-tab-panel').hide();
        $('#tab-' + tab).show();
        loadActiveTab();
    });

    $('#report-apply-btn').on('click', loadActiveTab);

    function loadActiveTab() {
        var tab = $('.inventory-tab.active').data('tab');
        if (tab === 'sales') loadSalesSummary();
        if (tab === 'top-items') loadTopItems();
        if (tab === 'stock') loadStockReport();
    }

    // ---------------- Sales Summary ----------------
    function loadSalesSummary() {
        ajax({ url: '/api/reports/sales-summary/', method: 'GET', data: currentRange() }).done(function (res) {
            $('#stat-total-orders').text(res.total_orders);
            $('#stat-total-revenue').text(window.CURRENCY + res.total_revenue);
            $('#stat-average-order').text(window.CURRENCY + res.average_order_value);

            var $body = $('#sales-daily-body').empty();
            if (!res.daily.length) {
                $body.append('<tr><td colspan="3" style="color:#888">No orders in this date range.</td></tr>');
                return;
            }
            res.daily.forEach(function (row) {
                var $row = $('<tr></tr>');
                $row.append($('<td></td>').text(row.date));
                $row.append($('<td></td>').text(row.orders));
                $row.append($('<td></td>').text(window.CURRENCY + row.revenue));
                $body.append($row);
            });
        });
    }

    // ---------------- Top-Selling Items ----------------
    function loadTopItems() {
        ajax({ url: '/api/reports/top-items/', method: 'GET', data: currentRange() }).done(function (res) {
            var $body = $('#top-items-body').empty();
            if (!res.items.length) {
                $body.append('<tr><td colspan="5" style="color:#888">No sales in this date range.</td></tr>');
                return;
            }
            res.items.forEach(function (row, index) {
                var $row = $('<tr></tr>');
                $row.append($('<td></td>').text(index + 1));
                $row.append($('<td></td>').text(row.item_name));
                $row.append($('<td></td>').text(row.variant_name));
                $row.append($('<td></td>').text(row.quantity_sold));
                $row.append($('<td></td>').text(window.CURRENCY + row.revenue));
                $body.append($row);
            });
        });
    }

    // ---------------- Stock Report ----------------
    function loadStockReport() {
        ajax({ url: '/api/reports/stock/', method: 'GET', data: currentRange() }).done(function (res) {
            $('#stock-stat-tracked').text(res.tracked_count);
            $('#stock-stat-low').text(res.low_stock_count);
            $('#stock-stat-out').text(res.out_of_stock_count);
            $('#stock-stat-total-units').text(res.total_units_in_stock);

            var $body = $('#stock-movement-body').empty();
            var labels = { sale: 'Sale', purchase: 'Purchase', adjustment: 'Adjustment' };
            Object.keys(labels).forEach(function (key) {
                var value = res.movement_totals[key] || 0;
                var $row = $('<tr></tr>');
                $row.append($('<td></td>').text(labels[key]));
                var $change = $('<td></td>').text((value > 0 ? '+' : '') + value);
                $change.css('color', value > 0 ? '#16a34a' : (value < 0 ? '#dc2626' : '')).css('font-weight', '700');
                $row.append($change);
                $body.append($row);
            });
        });
    }

    loadSalesSummary();
});
