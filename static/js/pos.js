$(function () {
    var cart = [];
    var menuData = [];
    var currentCategoryId = null;

    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    function loadMenu() {
        if (!navigator.onLine) {
            return loadMenuOffline();
        }
        ajax({ url: '/api/menu/', method: 'GET' }).done(function (res) {
            menuData = res.categories;
            renderCategoryTabs();
            if (menuData.length) {
                selectCategory(menuData[0].id);
            }
            // Mirror into IndexedDB so New Order keeps working if connectivity
            // drops later in this same session.
            posDb.saveMenu(res.categories).catch(function () {});
        }).fail(function () {
            // Online per navigator.onLine but the request still failed
            // (e.g. server unreachable) — fall back to the cached menu.
            loadMenuOffline();
        });
    }

    function loadMenuOffline() {
        posDb.loadMenuFromCache().then(function (categories) {
            menuData = categories;
            renderCategoryTabs();
            if (menuData.length) {
                selectCategory(menuData[0].id);
            } else {
                $('#item-grid').html('<p style="color:#888">No menu available offline yet — connect to the internet once to load it.</p>');
            }
        });
    }

    function renderCategoryTabs() {
        var $tabs = $('#category-tabs').empty();
        menuData.forEach(function (cat) {
            var $tab = $('<div class="category-tab"></div>').data('id', cat.id);
            $tab.append($('<span class="category-tab-name"></span>').text(cat.name));
            $tab.append($('<span class="category-tab-count"></span>').text(cat.items.length));
            $tab.on('click', function () {
                selectCategory(cat.id);
            });
            $tabs.append($tab);
        });
    }

    function selectCategory(catId) {
        currentCategoryId = catId;
        $('.category-tab').removeClass('active').each(function () {
            if ($(this).data('id') === catId) {
                $(this).addClass('active');
                var el = this;
                if (el.scrollIntoView) {
                    el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
                }
            }
        });
        renderItemGrid();
    }

    function renderItemGrid() {
        var cat = menuData.find(function (c) { return c.id === currentCategoryId; });
        var $grid = $('#item-grid').empty();
        if (!cat) return;
        cat.items.forEach(function (item) {
            var $card = $('<div class="item-card"></div>');
            if (item.image_url) {
                $card.append($('<img class="item-image">').attr('src', item.image_url).attr('alt', item.name));
            }
            $card.append($('<div class="item-name"></div>').text(item.name));
            if (item.description) {
                $card.append($('<div class="item-desc"></div>').text(item.description));
            }
            item.variants.forEach(function (variant) {
                var label = variant.name + ' — ' + window.CURRENCY + variant.price;
                var $btn = $('<button type="button" class="variant-btn"></button>').text(label);
                $btn.on('click', function () {
                    addToCart(item, variant);
                });
                $card.append($btn);
            });
            $grid.append($card);
        });
    }

    function addToCart(item, variant) {
        var existing = cart.find(function (line) { return line.variant_id === variant.id && !line.note; });
        if (existing) {
            existing.quantity += 1;
        } else {
            cart.push({
                variant_id: variant.id,
                item_name: item.name,
                variant_name: variant.name,
                unit_price: parseFloat(variant.price),
                quantity: 1,
                note: ''
            });
        }
        renderCart();
    }

    function renderCart() {
        var $lines = $('#cart-lines').empty();
        if (!cart.length) {
            $lines.append('<div class="empty-cart-note">No items added yet.</div>');
        }
        cart.forEach(function (line, idx) {
            var $row = $('<div class="cart-line"></div>');
            var label = line.item_name + ' (' + line.variant_name + ')';
            $row.append($('<div class="cart-line-name"></div>').text(label));

            var $controls = $('<div class="cart-line-controls"></div>');
            var $minus = $('<button type="button" class="qty-btn">-</button>').on('click', function () {
                line.quantity -= 1;
                if (line.quantity <= 0) cart.splice(idx, 1);
                renderCart();
            });
            var $qty = $('<span></span>').text(line.quantity);
            var $plus = $('<button type="button" class="qty-btn">+</button>').on('click', function () {
                line.quantity += 1;
                renderCart();
            });
            var $remove = $('<span class="remove-line">✕</span>').on('click', function () {
                cart.splice(idx, 1);
                renderCart();
            });
            $controls.append($minus, $qty, $plus, $remove);
            $row.append($controls);
            $lines.append($row);
        });
        recalcTotals();
        $('#place-order-btn').prop('disabled', cart.length === 0);
    }

    function subtotal() {
        return cart.reduce(function (sum, l) { return sum + l.unit_price * l.quantity; }, 0);
    }

    function recalcTotals() {
        var sub = subtotal();
        var discountType = $('#discount-type').val();
        var discountValue = parseFloat($('#discount-value').val()) || 0;
        var discount = 0;
        if (discountType === 'flat') {
            discount = Math.min(discountValue, sub);
        } else if (discountType === 'percent') {
            discount = sub * discountValue / 100;
        }
        var taxable = sub - discount;
        var taxPercent = parseFloat(window.TAX_PERCENT || 0);
        var tax = taxable * taxPercent / 100;
        var total = taxable + tax;

        $('#totals-subtotal').text(sub.toFixed(2));
        $('#totals-discount').text(discount.toFixed(2));
        $('#totals-tax').text(tax.toFixed(2));
        $('#totals-total').text(total.toFixed(2));
    }

    $('#discount-type, #discount-value').on('input change', recalcTotals);

    $('#order-type').on('change', function () {
        var type = $(this).val();
        $('#customer-field').toggle(type === 'delivery' || type === 'takeaway');
        $('#address-field').toggle(type === 'delivery');
    }).trigger('change');

    $('#place-order-btn').on('click', function () {
        if (!cart.length) return;
        $('#cart-error').text('');
        $(this).prop('disabled', true).text('Placing...');

        var payload = {
            order_type: $('#order-type').val(),
            customer_name: $('#customer-name').val(),
            customer_phone: $('#customer-phone').val(),
            delivery_address: $('#delivery-address').val(),
            discount_type: $('#discount-type').val(),
            discount_value: $('#discount-value').val() || 0,
            items: cart.map(function (l) {
                return { variant_id: l.variant_id, quantity: l.quantity, note: l.note };
            })
        };

        posSync.placeOrder(payload).then(function (result) {
            showReceipt(result.order, result.source === 'offline');
            resetOrderForm();
        }, function (xhr) {
            var msg = (xhr && xhr.responseJSON && xhr.responseJSON.error) || 'Something went wrong.';
            $('#cart-error').text(msg);
        }).finally(function () {
            $('#place-order-btn').prop('disabled', cart.length === 0).text('Punch Order');
        });
    });

    function resetOrderForm() {
        cart = [];
        $('#discount-type').val('none');
        $('#discount-value').val(0);
        $('#customer-name, #customer-phone, #delivery-address').val('');
        renderCart();
    }

    function showReceipt(order, isPendingSync) {
        var $content = $('#receipt-content').empty();
        $content.append('<h3>' + window.RESTAURANT_NAME_JS + '</h3>');
        if (isPendingSync) {
            $content.append('<div class="pending-sync-badge">⏳ Offline Order — Pending Sync</div>');
        }
        $content.append('<div class="receipt-meta" style="text-align:center">' + order.invoice_number + '<br>' + formatReceiptTimestamp(order.created_at) + '</div>');
        $content.append('<div class="receipt-meta">' + order.order_type_display + '</div>');
        $content.append('<div class="receipt-divider"></div>');

        order.lines.forEach(function (line) {
            var $l = $('<div class="receipt-line"></div>');
            $l.append($('<span></span>').text(line.quantity + ' x ' + line.item_name + ' (' + line.variant_name + ')'));
            $l.append($('<span></span>').text(window.CURRENCY + line.line_total));
            $content.append($l);
        });

        $content.append('<div class="receipt-divider"></div>');
        $content.append(receiptRow('Subtotal', order.subtotal));
        $content.append(receiptRow('Discount', order.discount_amount));
        $content.append(receiptRow('Tax', order.tax_amount));
        $content.append('<div class="receipt-divider"></div>');
        var $total = receiptRow('Total', order.total);
        $total.css('font-weight', '700').css('font-size', '15px');
        $content.append($total);
        $content.append(receiptRow('Payment', order.payment_method.toUpperCase()));

        $('#receipt-modal').css('display', 'flex');
    }

    function formatReceiptTimestamp(value) {
        // Server sends "YYYY-MM-DD HH:MM" already formatted; offline orders
        // store a raw ISO string (new Date().toISOString()) — normalize both
        // to the same display format.
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(value)) return value;
        var d = new Date(value);
        if (isNaN(d.getTime())) return value;
        var pad = function (n) { return String(n).padStart(2, '0'); };
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }

    function receiptRow(label, value) {
        var $row = $('<div class="receipt-line"></div>');
        $row.append($('<span></span>').text(label));
        $row.append($('<span></span>').text(typeof value === 'string' && isNaN(value) ? value : window.CURRENCY + value));
        return $row;
    }

    $('#print-receipt-btn').on('click', function () {
        window.print();
    });

    $('#new-order-btn').on('click', function () {
        $('#receipt-modal').hide();
    });

    function renderOfflineNotice() {
        $('#offline-mode-notice').toggle(!navigator.onLine);
    }
    window.addEventListener('online', function () {
        renderOfflineNotice();
        loadMenu(); // refresh with the authoritative server menu now that we're back
    });
    window.addEventListener('offline', renderOfflineNotice);
    renderOfflineNotice();

    loadMenu();
});
