$(function () {
    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    function loadQueue() {
        if (!navigator.onLine) {
            return renderOfflineOnly();
        }
        ajax({ url: '/api/orders/queue/', method: 'GET' }).done(function (res) {
            renderPendingSyncThenBoard(res.orders);
        }).fail(function () {
            renderOfflineOnly();
        });
    }

    // Kitchen view = server's active queue + any locally-created orders that
    // haven't synced yet. A not-yet-synced order has no server-assigned id,
    // so its status buttons stay disabled until posSync confirms it exists
    // server-side (see the "orders_synced" cleanup below).
    function renderPendingSyncThenBoard(serverOrders) {
        posDb.getAllOrders().then(function (localOrders) {
            var pendingLocal = localOrders.filter(function (o) {
                return o.status === 'PENDING_SYNC' || o.status === 'FAILED';
            });
            renderBoard(pendingLocal.concat(serverOrders));
        }).catch(function () {
            renderBoard(serverOrders);
        });
    }

    function renderOfflineOnly() {
        posDb.getAllOrders().then(function (localOrders) {
            var pendingLocal = localOrders.filter(function (o) {
                return o.status === 'PENDING_SYNC' || o.status === 'FAILED';
            });
            $('#kitchen-offline-note').show();
            renderBoard(pendingLocal);
        });
    }

    function renderBoard(orders) {
        var $board = $('#kitchen-board').empty();
        if (!orders.length) {
            $board.append('<p style="color:#888">No active orders right now.</p>');
            return;
        }
        orders.forEach(function (order) {
            var isPendingSync = !!order.is_offline;
            var statusKey = isPendingSync ? 'pending_sync' : order.status;
            var $card = $('<div class="kitchen-card"></div>').addClass('status-' + statusKey);

            var $header = $('<div class="kitchen-card-header"></div>');
            $header.append($('<span></span>').text(order.invoice_number));
            $header.append($('<span></span>').text(isPendingSync ? 'Pending Sync' : order.status_display));
            $card.append($header);

            $card.append($('<div class="kitchen-card-meta"></div>').text(order.order_type_display));

            order.lines.forEach(function (line) {
                var text = line.quantity + ' x ' + line.item_name + ' (' + line.variant_name + ')';
                if (line.note) text += ' — ' + line.note;
                $card.append($('<div class="kitchen-line"></div>').text(text));
            });

            var $actions = $('<div class="kitchen-actions"></div>');
            if (isPendingSync) {
                $actions.append(
                    $('<span class="pending-sync-note"></span>').text('Waiting to sync — actions unlock once confirmed')
                );
            } else {
                if (order.status === 'pending') {
                    $actions.append(actionBtn('Start', 'btn-progress', order.id, 'in_progress'));
                }
                if (order.status === 'in_progress') {
                    $actions.append(actionBtn('Complete', 'btn-complete', order.id, 'completed'));
                }
                $actions.append(actionBtn('Cancel', 'btn-cancel', order.id, 'cancelled'));
            }
            $card.append($actions);

            $board.append($card);
        });
    }

    function actionBtn(label, cls, orderId, status) {
        return $('<button type="button"></button>').addClass(cls).text(label).on('click', function () {
            updateStatus(orderId, status);
        });
    }

    function updateStatus(orderId, status) {
        ajax({
            url: '/api/orders/' + orderId + '/status/',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ status: status })
        }).done(function () {
            loadQueue();
        });
    }

    window.addEventListener('online', function () {
        $('#kitchen-offline-note').hide();
        loadQueue();
    });
    window.addEventListener('offline', loadQueue);

    // Once an order finishes syncing elsewhere in the app (e.g. the sync
    // engine drains the queue while this tab is open), refresh so it moves
    // from "Pending Sync" into the normal server-driven queue.
    if (window.posSync) {
        posSync.onSyncEvent(function (event) {
            if (event === 'order_synced' || event === 'sync_complete') loadQueue();
        });
    }

    loadQueue();
    setInterval(loadQueue, 10000);
});
