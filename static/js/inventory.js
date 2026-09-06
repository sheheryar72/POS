$(function () {
    var variantsCache = [];

    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    // ---------------- Tabs ----------------
    $('.inventory-tab').on('click', function () {
        var tab = $(this).data('tab');
        $('.inventory-tab').removeClass('active');
        $(this).addClass('active');
        $('.inventory-tab-panel').hide();
        $('#tab-' + tab).show();

        if (tab === 'overview') loadOverview();
        if (tab === 'adjust') loadVariantsForAdjust();
        if (tab === 'history') loadHistory();
    });

    // ---------------- Stock Overview ----------------
    function loadOverview() {
        ajax({ url: '/api/inventory/overview/', method: 'GET' }).done(function (res) {
            $('#stat-tracked-count').text(res.tracked_count);
            $('#stat-low-count').text(res.low_stock.length);
            $('#stat-out-count').text(res.out_of_stock.length);
            renderStockTable('#out-of-stock-body', res.out_of_stock, 'No out-of-stock items.');
            renderStockTable('#low-stock-body', res.low_stock, 'No low-stock items.');
        });
    }

    function renderStockTable(selector, rows, emptyMessage) {
        var $body = $(selector).empty();
        if (!rows.length) {
            $body.append('<tr><td colspan="5" style="color:#888">' + emptyMessage + '</td></tr>');
            return;
        }
        rows.forEach(function (row) {
            var $row = $('<tr></tr>');
            $row.append($('<td></td>').text(row.category_name));
            $row.append($('<td></td>').text(row.item_name));
            $row.append($('<td></td>').text(row.variant_name));
            $row.append($('<td></td>').text(row.stock_quantity));
            $row.append($('<td></td>').text(row.low_stock_threshold));
            $body.append($row);
        });
    }

    // ---------------- Stock Adjustment ----------------
    function loadVariantsForAdjust() {
        ajax({ url: '/api/inventory/variants/', method: 'GET' }).done(function (res) {
            variantsCache = res.variants;
            var $select = $('#adjust-variant-select').empty();
            if (!variantsCache.length) {
                $select.append('<option value="">No stock-tracked items yet</option>');
                $('#adjust-current-stock').text('-');
                return;
            }
            variantsCache.forEach(function (v) {
                var label = v.item_name + ' (' + v.variant_name + ')';
                $select.append($('<option></option>').val(v.id).text(label));
            });
            updateCurrentStockDisplay();
        });
    }

    $('#adjust-variant-select').on('change', updateCurrentStockDisplay);

    function updateCurrentStockDisplay() {
        var variantId = parseInt($('#adjust-variant-select').val(), 10);
        var variant = variantsCache.find(function (v) { return v.id === variantId; });
        $('#adjust-current-stock').text(variant ? variant.stock_quantity : '-');
    }

    $('#adjust-type-select').on('change', function () {
        var type = $(this).val();
        if (type === 'purchase') {
            $('#adjust-quantity-label').text('Quantity Received');
            $('#adjust-quantity-hint').text('Enter how many units were purchased/received.');
            $('#adjust-quantity-input').attr('min', '1');
        } else {
            $('#adjust-quantity-label').text('Adjustment (+/-)');
            $('#adjust-quantity-hint').text('Positive to add stock, negative to remove (e.g. spoilage, theft, miscount).');
            $('#adjust-quantity-input').removeAttr('min');
        }
    }).trigger('change');

    $('#adjust-submit-btn').on('click', function () {
        var variantId = $('#adjust-variant-select').val();
        var movementType = $('#adjust-type-select').val();
        var quantity = $('#adjust-quantity-input').val();
        var note = $('#adjust-note-input').val();
        $('#adjust-error').text('');

        if (!variantId) {
            $('#adjust-error').text('Select an item first.');
            return;
        }
        if (!quantity) {
            $('#adjust-error').text('Enter a quantity.');
            return;
        }

        $(this).prop('disabled', true);
        ajax({
            url: '/api/inventory/adjust/',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                variant_id: variantId,
                movement_type: movementType,
                quantity: quantity,
                note: note,
            }),
        }).done(function () {
            $('#adjust-quantity-input').val('');
            $('#adjust-note-input').val('');
            loadVariantsForAdjust();
        }).fail(function (xhr) {
            $('#adjust-error').text((xhr.responseJSON && xhr.responseJSON.error) || 'Failed to record movement.');
        }).always(function () {
            $('#adjust-submit-btn').prop('disabled', false);
        });
    });

    // ---------------- Stock History ----------------
    function loadHistory() {
        var params = {};
        var date = $('#history-filter-date').val();
        var type = $('#history-filter-type').val();
        if (date) params.date = date;
        if (type) params.movement_type = type;

        ajax({ url: '/api/inventory/history/', method: 'GET', data: params }).done(function (res) {
            renderHistoryTable(res.movements);
        });
    }

    function renderHistoryTable(movements) {
        var $body = $('#history-body').empty();
        if (!movements.length) {
            $body.append('<tr><td colspan="7" style="color:#888">No stock movements found.</td></tr>');
            return;
        }
        movements.forEach(function (m) {
            var $row = $('<tr></tr>');
            $row.append($('<td></td>').text(m.created_at));
            $row.append($('<td></td>').text(m.item_name + ' (' + m.variant_name + ')'));
            $row.append($('<td></td>').text(m.movement_type_display));
            var $change = $('<td></td>').text((m.quantity_change > 0 ? '+' : '') + m.quantity_change);
            $change.css('color', m.quantity_change > 0 ? '#16a34a' : '#dc2626').css('font-weight', '700');
            $row.append($change);
            $row.append($('<td></td>').text(m.resulting_quantity));
            $row.append($('<td></td>').text(m.note));
            $row.append($('<td></td>').text(m.created_by));
            $body.append($row);
        });
    }

    $('#history-filter-date, #history-filter-type').on('change', loadHistory);

    loadOverview();
});
