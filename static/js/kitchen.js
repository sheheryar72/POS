$(function () {
    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    function loadQueue() {
        ajax({ url: '/api/orders/queue/', method: 'GET' }).done(function (res) {
            renderBoard(res.orders);
        });
    }

    function renderBoard(orders) {
        var $board = $('#kitchen-board').empty();
        if (!orders.length) {
            $board.append('<p style="color:#888">No active orders right now.</p>');
            return;
        }
        orders.forEach(function (order) {
            var $card = $('<div class="kitchen-card"></div>').addClass('status-' + order.status);
            var $header = $('<div class="kitchen-card-header"></div>');
            $header.append($('<span></span>').text(order.invoice_number));
            $header.append($('<span></span>').text(order.status_display));
            $card.append($header);

            $card.append($('<div class="kitchen-card-meta"></div>').text(order.order_type_display));

            order.lines.forEach(function (line) {
                var text = line.quantity + ' x ' + line.item_name + ' (' + line.variant_name + ')';
                if (line.note) text += ' — ' + line.note;
                $card.append($('<div class="kitchen-line"></div>').text(text));
            });

            var $actions = $('<div class="kitchen-actions"></div>');
            if (order.status === 'pending') {
                $actions.append(actionBtn('Start', 'btn-progress', order.id, 'in_progress'));
            }
            if (order.status === 'in_progress') {
                $actions.append(actionBtn('Complete', 'btn-complete', order.id, 'completed'));
            }
            $actions.append(actionBtn('Cancel', 'btn-cancel', order.id, 'cancelled'));
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

    loadQueue();
    setInterval(loadQueue, 10000);
});
