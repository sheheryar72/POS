/*
 * IndexedDB access layer for offline POS support.
 *
 * Schema (database "bb_pos", versioned below):
 *
 *   categories   — mirror of menu.Category      (id, name, sort_order, is_active)
 *   items        — mirror of menu.MenuItem      (id, category_id, name, description,
 *                                                 image_url, is_available, sort_order)
 *   variants     — mirror of menu.ItemVariant    (id, item_id, name, price, is_available)
 *   orders       — orders created on this device, offline or online, kept locally
 *                  as a receipt/audit trail (status: PENDING_SYNC | SYNCED | FAILED)
 *   pending_sync — sync queue: one row per order awaiting a server round-trip
 *                  (local_order_id, payload, status, retry_count, last_error, timestamps)
 *   sync_errors  — permanent record of sync failures, kept even after a later
 *                  retry succeeds, so nothing is silently lost from history
 *   app_meta     — small key/value store (device_id, last_menu_sync_at, etc.)
 *
 * Deliberately NOT stored here: customers (this app has no separate Customer
 * model — customer_name/phone/address are free-text fields directly on the
 * Order), taxes/payment methods (a single tax_percent lives on the
 * Restaurant row and is mirrored into app_meta; payment is cash-only system
 * wide, nothing to look up), inventory/stock (no stock model exists in this
 * app — see the offline capability notes shipped alongside this file).
 */

(function (global) {
    'use strict';

    var DB_NAME = 'bb_pos';
    var DB_VERSION = 1;
    var db = null;
    var dbOpenPromise = null;

    function openDb() {
        if (dbOpenPromise) return dbOpenPromise;

        dbOpenPromise = new Promise(function (resolve, reject) {
            var req = indexedDB.open(DB_NAME, DB_VERSION);

            req.onupgradeneeded = function (event) {
                var database = event.target.result;

                if (!database.objectStoreNames.contains('categories')) {
                    database.createObjectStore('categories', { keyPath: 'id' });
                }
                if (!database.objectStoreNames.contains('items')) {
                    var itemStore = database.createObjectStore('items', { keyPath: 'id' });
                    itemStore.createIndex('category_id', 'category_id', { unique: false });
                }
                if (!database.objectStoreNames.contains('variants')) {
                    var variantStore = database.createObjectStore('variants', { keyPath: 'id' });
                    variantStore.createIndex('item_id', 'item_id', { unique: false });
                }
                if (!database.objectStoreNames.contains('orders')) {
                    var orderStore = database.createObjectStore('orders', { keyPath: 'client_transaction_id' });
                    orderStore.createIndex('status', 'status', { unique: false });
                    orderStore.createIndex('created_at', 'created_at', { unique: false });
                }
                if (!database.objectStoreNames.contains('pending_sync')) {
                    var syncStore = database.createObjectStore('pending_sync', { keyPath: 'local_order_id' });
                    syncStore.createIndex('status', 'status', { unique: false });
                    syncStore.createIndex('created_at', 'created_at', { unique: false });
                }
                if (!database.objectStoreNames.contains('sync_errors')) {
                    var errStore = database.createObjectStore('sync_errors', { keyPath: 'id', autoIncrement: true });
                    errStore.createIndex('local_order_id', 'local_order_id', { unique: false });
                }
                if (!database.objectStoreNames.contains('app_meta')) {
                    database.createObjectStore('app_meta', { keyPath: 'key' });
                }
            };

            req.onsuccess = function (event) {
                db = event.target.result;
                resolve(db);
            };
            req.onerror = function (event) {
                reject(event.target.error);
            };
        });

        return dbOpenPromise;
    }

    function tx(storeNames, mode) {
        return openDb().then(function (database) {
            return database.transaction(storeNames, mode);
        });
    }

    function reqToPromise(req) {
        return new Promise(function (resolve, reject) {
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
    }

    function putAll(storeName, records) {
        return tx([storeName], 'readwrite').then(function (t) {
            return new Promise(function (resolve, reject) {
                var store = t.objectStore(storeName);
                records.forEach(function (r) { store.put(r); });
                t.oncomplete = function () { resolve(); };
                t.onerror = function () { reject(t.error); };
            });
        });
    }

    function clearAndPutAll(storeName, records) {
        return tx([storeName], 'readwrite').then(function (t) {
            return new Promise(function (resolve, reject) {
                var store = t.objectStore(storeName);
                var clearReq = store.clear();
                clearReq.onsuccess = function () {
                    records.forEach(function (r) { store.put(r); });
                };
                t.oncomplete = function () { resolve(); };
                t.onerror = function () { reject(t.error); };
            });
        });
    }

    function getAll(storeName) {
        return tx([storeName], 'readonly').then(function (t) {
            return reqToPromise(t.objectStore(storeName).getAll());
        });
    }

    function get(storeName, key) {
        return tx([storeName], 'readonly').then(function (t) {
            return reqToPromise(t.objectStore(storeName).get(key));
        });
    }

    function put(storeName, record) {
        return tx([storeName], 'readwrite').then(function (t) {
            return new Promise(function (resolve, reject) {
                t.objectStore(storeName).put(record);
                t.oncomplete = function () { resolve(record); };
                t.onerror = function () { reject(t.error); };
            });
        });
    }

    function deleteRecord(storeName, key) {
        return tx([storeName], 'readwrite').then(function (t) {
            return new Promise(function (resolve, reject) {
                t.objectStore(storeName).delete(key);
                t.oncomplete = function () { resolve(); };
                t.onerror = function () { reject(t.error); };
            });
        });
    }

    function getAllByIndex(storeName, indexName, value) {
        return tx([storeName], 'readonly').then(function (t) {
            return reqToPromise(t.objectStore(storeName).index(indexName).getAll(value));
        });
    }

    // ---- Master data (categories/items/variants) ----

    function saveMenu(categories) {
        var categoryRows = [];
        var itemRows = [];
        var variantRows = [];

        categories.forEach(function (cat) {
            categoryRows.push({ id: cat.id, name: cat.name, item_count: cat.items.length });
            cat.items.forEach(function (item) {
                itemRows.push({
                    id: item.id,
                    category_id: cat.id,
                    name: item.name,
                    description: item.description || '',
                    image_url: item.image_url || '',
                });
                item.variants.forEach(function (variant) {
                    variantRows.push({
                        id: variant.id,
                        item_id: item.id,
                        name: variant.name,
                        price: variant.price,
                    });
                });
            });
        });

        return Promise.all([
            clearAndPutAll('categories', categoryRows),
            clearAndPutAll('items', itemRows),
            clearAndPutAll('variants', variantRows),
        ]).then(function () {
            return setMeta('last_menu_sync_at', new Date().toISOString());
        });
    }

    function loadMenuFromCache() {
        return Promise.all([getAll('categories'), getAll('items'), getAll('variants')]).then(function (results) {
            var categories = results[0];
            var items = results[1];
            var variants = results[2];

            var itemsByCategory = {};
            items.forEach(function (item) {
                if (!itemsByCategory[item.category_id]) itemsByCategory[item.category_id] = [];
                itemsByCategory[item.category_id].push(item);
            });
            var variantsByItem = {};
            variants.forEach(function (v) {
                if (!variantsByItem[v.item_id]) variantsByItem[v.item_id] = [];
                variantsByItem[v.item_id].push(v);
            });

            return categories
                .map(function (cat) {
                    var catItems = (itemsByCategory[cat.id] || []).map(function (item) {
                        return {
                            id: item.id,
                            name: item.name,
                            description: item.description,
                            image_url: item.image_url,
                            variants: (variantsByItem[item.id] || []).map(function (v) {
                                return { id: v.id, name: v.name, price: v.price };
                            }),
                        };
                    }).filter(function (item) { return item.variants.length > 0; });
                    return { id: cat.id, name: cat.name, items: catItems };
                })
                .filter(function (cat) { return cat.items.length > 0; });
        });
    }

    // ---- app_meta (key/value) ----

    function setMeta(key, value) {
        return put('app_meta', { key: key, value: value });
    }

    function getMeta(key) {
        return get('app_meta', key).then(function (row) {
            return row ? row.value : null;
        });
    }

    // ---- Orders + sync queue ----

    function saveOrderLocally(order) {
        return put('orders', order);
    }

    function updateOrderStatus(clientTransactionId, status, extra) {
        return get('orders', clientTransactionId).then(function (order) {
            if (!order) return null;
            order.status = status;
            if (extra) Object.assign(order, extra);
            return put('orders', order);
        });
    }

    function getAllOrders() {
        return getAll('orders');
    }

    function enqueueSync(localOrderId, payload) {
        return put('pending_sync', {
            local_order_id: localOrderId,
            operation: 'create_order',
            payload: payload,
            status: 'PENDING',
            retry_count: 0,
            last_error: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
        });
    }

    function getPendingSyncQueueFIFO() {
        return getAll('pending_sync').then(function (rows) {
            return rows
                .filter(function (r) { return r.status === 'PENDING' || r.status === 'FAILED'; })
                .sort(function (a, b) { return new Date(a.created_at) - new Date(b.created_at); });
        });
    }

    function updateSyncEntry(localOrderId, fields) {
        return get('pending_sync', localOrderId).then(function (row) {
            if (!row) return null;
            Object.assign(row, fields, { updated_at: new Date().toISOString() });
            return put('pending_sync', row);
        });
    }

    function removeSyncEntry(localOrderId) {
        return deleteRecord('pending_sync', localOrderId);
    }

    function recordSyncError(localOrderId, message) {
        return put('sync_errors', {
            local_order_id: localOrderId,
            message: message,
            at: new Date().toISOString(),
        });
    }

    global.posDb = {
        openDb: openDb,
        saveMenu: saveMenu,
        loadMenuFromCache: loadMenuFromCache,
        setMeta: setMeta,
        getMeta: getMeta,
        saveOrderLocally: saveOrderLocally,
        updateOrderStatus: updateOrderStatus,
        getAllOrders: getAllOrders,
        enqueueSync: enqueueSync,
        getPendingSyncQueueFIFO: getPendingSyncQueueFIFO,
        updateSyncEntry: updateSyncEntry,
        removeSyncEntry: removeSyncEntry,
        recordSyncError: recordSyncError,
        getAllByIndex: getAllByIndex,
    };
})(window);
