$(function () {
    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    function loadSummary() {
        ajax({ url: '/api/dashboard/summary/', method: 'GET' }).done(function (res) {
            $('#stat-total-orders').text(res.total_orders);
            $('#stat-total-revenue').text(window.CURRENCY + res.total_revenue);
            $('#stat-pending').text(res.pending_count);
            $('#stat-in-progress').text(res.in_progress_count);
            $('#stat-completed').text(res.completed_count);
        });
    }

    loadSummary();
    setInterval(loadSummary, 20000);
});
