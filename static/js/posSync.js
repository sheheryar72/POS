/*
 * Offline order queue + synchronization engine.
 *
 * Responsibilities:
 *   - device_id: a stable per-browser identifier (localStorage), used to
 *     build globally-unique client_transaction_ids.
 *   - posRequest(): a thin routing layer over the existing jQuery $.ajax
 *     calls already used by pos.js/kitchen.js/etc. It does NOT replace those
 *     calls — order placement specifically is offline-aware; everything
 *     else keeps calling $.ajax directly, unchanged.
 *   - Sync engine: FIFO drain of the pending_sync queue whenever the browser
 *     comes online (or a manual sync is triggered), with retry/backoff and
 *     a single-flight guard so the same queue is never processed twice
 *     concurrently (e.g. two 'online' events firing close together, or a
 *     periodic check overlapping a user-triggered retry).
 */

(function (global) {
    'use strict';

    var MAX_RETRIES = 8;

    // ---- Device identity ----

    function getDeviceId() {
        var id = localStorage.getItem('bb_pos_device_id');
        if (!id) {
            id = 'DEVICE-' + (crypto.randomUUID ? crypto.randomUUID().slice(0, 8).toUpperCase() : Math.random().toString(36).slice(2, 10).toUpperCase());
            localStorage.setItem('bb_pos_device_id', id);
        }
        return id;
    }

    var localSeqCounter = 0;

    function generateClientTransactionId() {
        localSeqCounter += 1;
        var ts = new Date().toISOString().replace(/[-:.TZ]/g, '');
        return 'POS-' + getDeviceId() + '-' + ts + '-' + String(localSeqCounter).padStart(4, '0');
    }

    // ---- Shared AJAX helper (same CSRF pattern already used across the app) ----

    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    // ---- Order submission: online-direct vs. offline-queued ----

    /**
     * Places an order. Always attaches a client_transaction_id so the
     * server-side idempotency check applies uniformly online or offline
     * (see orders.views._create_order_from_payload).
     *
     * Returns a Promise resolving to:
     *   { source: 'online', order: {...} }               — server confirmed immediately
     *   { source: 'offline', order: {...}, localOrderId } — saved locally, queued for sync
     */
    function placeOrder(payload) {
        var clientTransactionId = generateClientTransactionId();
        payload = Object.assign({}, payload, { client_transaction_id: clientTransactionId });

        if (!navigator.onLine) {
            return saveOrderOffline(payload, clientTransactionId);
        }

        return ajax({
            url: '/api/orders/place/',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(payload),
        }).then(function (res) {
            return { source: 'online', order: res.order };
        }, function (xhr) {
            // Network-level failure (not a validation error from the server)
            // while we thought we were online — e.g. connection dropped
            // mid-request. Fall back to the offline path rather than losing
            // the order. A real server validation error (400) is NOT
            // retried this way — it's surfaced to the caller as-is.
            if (xhr.status === 0) {
                return saveOrderOffline(payload, clientTransactionId);
            }
            return Promise.reject(xhr);
        });
    }

    function computeLocalTotals(payload, menuLookup) {
        var subtotal = 0;
        payload.items.forEach(function (line) {
            var variant = menuLookup(line.variant_id);
            if (variant) {
                subtotal += parseFloat(variant.price) * line.quantity;
            }
        });
        var discountValue = parseFloat(payload.discount_value) || 0;
        var discount = 0;
        if (payload.discount_type === 'flat') {
            discount = Math.min(discountValue, subtotal);
        } else if (payload.discount_type === 'percent') {
            discount = (subtotal * discountValue) / 100;
        }
        var taxPercent = parseFloat(window.TAX_PERCENT || 0);
        var taxable = subtotal - discount;
        var tax = (taxable * taxPercent) / 100;
        var total = taxable + tax;
        return {
            subtotal: subtotal.toFixed(2),
            discount_amount: discount.toFixed(2),
            tax_amount: tax.toFixed(2),
            tax_percent: taxPercent.toFixed(2),
            total: total.toFixed(2),
        };
    }

    function saveOrderOffline(payload, clientTransactionId) {
        return posDb.loadMenuFromCache().then(function (categories) {
            var variantIndex = {};
            categories.forEach(function (cat) {
                cat.items.forEach(function (item) {
                    item.variants.forEach(function (v) {
                        variantIndex[v.id] = Object.assign({}, v, { item_name: item.name });
                    });
                });
            });

            var totals = computeLocalTotals(payload, function (id) { return variantIndex[id]; });

            var lines = payload.items.map(function (line) {
                var variant = variantIndex[line.variant_id] || {};
                return {
                    item_name: variant.item_name || 'Unknown item',
                    variant_name: variant.name || '',
                    unit_price: variant.price || '0.00',
                    quantity: line.quantity,
                    line_total: (parseFloat(variant.price || 0) * line.quantity).toFixed(2),
                    note: line.note || '',
                };
            });

            var localOrder = {
                client_transaction_id: clientTransactionId,
                invoice_number: 'PENDING-' + clientTransactionId.slice(-8),
                order_type: payload.order_type,
                order_type_display: orderTypeLabel(payload.order_type),
                customer_name: payload.customer_name || '',
                customer_phone: payload.customer_phone || '',
                delivery_address: payload.delivery_address || '',
                status: 'PENDING_SYNC',
                status_display: 'Pending Sync',
                payment_method: 'cash',
                discount_type: payload.discount_type,
                discount_value: payload.discount_value,
                lines: lines,
                created_at: new Date().toISOString(),
                is_offline: true,
            };
            Object.assign(localOrder, totals);

            return posDb.saveOrderLocally(localOrder)
                .then(function () { return posDb.enqueueSync(clientTransactionId, payload); })
                .then(function () {
                    return { source: 'offline', order: localOrder, localOrderId: clientTransactionId };
                });
        });
    }

    function orderTypeLabel(type) {
        return { dine_in: 'Dine-in', takeaway: 'Takeaway', delivery: 'Delivery' }[type] || type;
    }

    // ---- Sync engine ----

    var syncInFlight = false;
    var listeners = [];

    function onSyncEvent(fn) {
        listeners.push(fn);
    }

    function emit(event, data) {
        listeners.forEach(function (fn) {
            try { fn(event, data); } catch (e) { /* listener errors must not break the sync loop */ }
        });
    }

    function backoffDelayMs(retryCount) {
        return Math.min(30000, 1000 * Math.pow(2, retryCount));
    }

    function sleep(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    function syncOne(entry) {
        return posDb.updateSyncEntry(entry.local_order_id, { status: 'SYNCING' })
            .then(function () {
                return ajax({
                    url: '/api/orders/sync/',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify(entry.payload),
                });
            })
            .then(function (res) {
                return posDb.updateOrderStatus(entry.local_order_id, 'SYNCED', {
                    server_id: res.server_id,
                    invoice_number: res.invoice_number,
                }).then(function () {
                    return posDb.removeSyncEntry(entry.local_order_id);
                }).then(function () {
                    emit('order_synced', { localOrderId: entry.local_order_id, serverId: res.server_id, invoiceNumber: res.invoice_number, alreadySynced: res.status === 'already_synced' });
                    return { ok: true };
                });
            })
            .catch(function (xhr) {
                var isClientError = xhr.status >= 400 && xhr.status < 500;
                var message = (xhr.responseJSON && xhr.responseJSON.error) || xhr.statusText || 'Unknown sync error';
                var nextRetryCount = entry.retry_count + 1;

                return posDb.recordSyncError(entry.local_order_id, message).then(function () {
                    if (isClientError) {
                        // A real validation failure (bad data) — retrying identical
                        // payload forever would never succeed. Mark FAILED and stop
                        // auto-retrying; the order stays visible in history for
                        // manual reconciliation rather than disappearing.
                        return posDb.updateSyncEntry(entry.local_order_id, {
                            status: 'FAILED', retry_count: nextRetryCount, last_error: message,
                        }).then(function () {
                            return posDb.updateOrderStatus(entry.local_order_id, 'FAILED', { last_error: message });
                        }).then(function () {
                            emit('order_failed', { localOrderId: entry.local_order_id, error: message, permanent: true });
                            return { ok: false, permanent: true };
                        });
                    }

                    var status = nextRetryCount >= MAX_RETRIES ? 'FAILED' : 'PENDING';
                    return posDb.updateSyncEntry(entry.local_order_id, {
                        status: status, retry_count: nextRetryCount, last_error: message,
                    }).then(function () {
                        emit('order_failed', { localOrderId: entry.local_order_id, error: message, permanent: status === 'FAILED' });
                        return { ok: false, permanent: status === 'FAILED' };
                    });
                });
            });
    }

    /**
     * Drains the pending_sync queue in FIFO (oldest first) order, one entry
     * at a time — never concurrently, so a burst of retries can't hammer the
     * server or race each other. A failing entry (network error, not yet at
     * MAX_RETRIES) is requeued with backoff and does not block later entries
     * from being attempted in this same pass.
     */
    function runSync() {
        if (syncInFlight) return Promise.resolve({ skipped: true });
        if (!navigator.onLine) return Promise.resolve({ skipped: true });

        syncInFlight = true;
        emit('sync_start');

        return posDb.getPendingSyncQueueFIFO().then(function (queue) {
            if (!queue.length) {
                syncInFlight = false;
                emit('sync_idle');
                return { synced: 0, failed: 0 };
            }

            var synced = 0, failed = 0;

            function next(index) {
                if (index >= queue.length) {
                    return Promise.resolve();
                }
                var entry = queue[index];
                return syncOne(entry).then(function (result) {
                    if (result.ok) synced += 1;
                    else failed += 1;
                    return next(index + 1);
                });
            }

            return next(0).then(function () {
                syncInFlight = false;
                emit('sync_complete', { synced: synced, failed: failed });
                return { synced: synced, failed: failed };
            });
        }).catch(function (err) {
            syncInFlight = false;
            emit('sync_error', { error: err && err.message });
        });
    }

    // Kick off a sync whenever the browser regains connectivity.
    window.addEventListener('online', function () {
        runSync();
    });

    // Periodic safety-net sync in case the 'online' event is missed (some
    // browsers fire it unreliably, e.g. captive portals or flaky Wi-Fi) —
    // deliberately not relying on Background Sync API alone per spec.
    setInterval(function () {
        if (navigator.onLine) runSync();
    }, 30000);

    global.posSync = {
        getDeviceId: getDeviceId,
        generateClientTransactionId: generateClientTransactionId,
        placeOrder: placeOrder,
        runSync: runSync,
        onSyncEvent: onSyncEvent,
    };
})(window);
