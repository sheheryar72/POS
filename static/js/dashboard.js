$(function () {
    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    var TITLES = { today: "Today's Summary", month: "This Month's Summary", all: 'All-Time Summary' };

    function loadSummary() {
        var period = $('#filter-period').val();
        ajax({ url: '/api/dashboard/summary/', method: 'GET', data: { period: period } }).done(function (res) {
            $('#dashboard-title').text(TITLES[res.period] || TITLES.today);
            $('#stat-total-orders').text(res.total_orders);
            $('#stat-total-revenue').text(window.CURRENCY + res.total_revenue);
            $('#stat-pending').text(res.pending_count);
            $('#stat-in-progress').text(res.in_progress_count);
            $('#stat-completed').text(res.completed_count);
        });
    }

    $('#apply-period-btn').on('click', loadSummary);

    loadSummary();
    setInterval(loadSummary, 20000);
});
