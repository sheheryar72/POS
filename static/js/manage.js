$(function () {
    var categories = [];
    var currentCategoryId = null;
    var currentItems = [];
    var editingItemId = null;

    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    function loadCategories() {
        ajax({ url: '/api/manage/categories/', method: 'GET' }).done(function (res) {
            categories = res.categories;
            renderCategoryList();
            if (!currentCategoryId && categories.length) {
                selectCategory(categories[0].id);
            } else if (currentCategoryId) {
                loadItems();
            }
        });
    }

    function renderCategoryList() {
        var $list = $('#category-list').empty();
        categories.forEach(function (cat) {
            var $row = $('<div class="category-row"></div>').data('id', cat.id);
            if (cat.id === currentCategoryId) $row.addClass('active');
            if (!cat.is_active) $row.addClass('inactive');

            var $name = $('<span></span>').text(cat.name);
            var $count = $('<span class="cat-count"></span>').text(cat.item_count);
            var $left = $('<div></div>').append($name);

            var $actions = $('<div class="category-row-actions"></div>');
            var $rename = $('<span>Rename</span>').on('click', function (e) {
                e.stopPropagation();
                renameCategory(cat);
            });
            var $toggle = $('<span></span>').text(cat.is_active ? 'Hide' : 'Show').on('click', function (e) {
                e.stopPropagation();
                toggleCategoryActive(cat);
            });
            var $del = $('<span class="del-cat">Delete</span>').on('click', function (e) {
                e.stopPropagation();
                deleteCategory(cat);
            });
            $actions.append($rename, $toggle, $del);

            $row.append($left, $count, $actions).on('click', function () {
                selectCategory(cat.id);
            });
            $list.append($row);
        });
    }

    function selectCategory(catId) {
        currentCategoryId = catId;
        var cat = categories.find(function (c) { return c.id === catId; });
        $('#items-heading').text(cat ? 'Items — ' + cat.name : 'Items');
        $('#add-item-btn').prop('disabled', false);
        renderCategoryList();
        loadItems();
    }

    function loadItems() {
        if (!currentCategoryId) return;
        ajax({ url: '/api/manage/items/?category_id=' + currentCategoryId, method: 'GET' }).done(function (res) {
            currentItems = res.items;
            renderItemsList();
        });
    }

    function renderItemsList() {
        var $grid = $('#items-list').empty();
        if (!currentItems.length) {
            $grid.append('<p style="color:#888">No items in this category yet.</p>');
            return;
        }
        currentItems.forEach(function (item) {
            var $card = $('<div class="manage-item-card"></div>');
            if (!item.is_available) $card.addClass('unavailable');
            if (item.image_url) {
                $card.append($('<img>').attr('src', item.image_url));
            }
            if (!item.is_available) {
                $card.append('<span class="unavailable-badge">Hidden</span>');
            }
            $card.append($('<div class="mi-name"></div>').text(item.name));
            var priceLabel = item.variants.map(function (v) {
                return v.name + ': ' + window.CURRENCY + v.price;
            }).join(', ');
            $card.append($('<div class="mi-price"></div>').text(priceLabel));
            $card.on('click', function () { openItemModal(item); });
            $grid.append($card);
        });
    }

    /* ---------- Category modal ---------- */
    var categoryEditing = null;

    function openCategoryModal(cat) {
        categoryEditing = cat || null;
        $('#category-modal-title').text(cat ? 'Rename Category' : 'Add Category');
        $('#category-name-input').val(cat ? cat.name : '');
        $('#category-modal-error').text('');
        $('#category-modal').css('display', 'flex');
        $('#category-name-input').focus();
    }

    function renameCategory(cat) {
        openCategoryModal(cat);
    }

    $('#add-category-btn').on('click', function () { openCategoryModal(null); });
    $('#category-cancel-btn').on('click', function () { $('#category-modal').hide(); });

    $('#category-save-btn').on('click', function () {
        var name = $('#category-name-input').val().trim();
        if (!name) {
            $('#category-modal-error').text('Name is required.');
            return;
        }
        if (categoryEditing) {
            ajax({
                url: '/api/manage/categories/' + categoryEditing.id + '/',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ name: name })
            }).done(function () {
                $('#category-modal').hide();
                loadCategories();
            }).fail(function (xhr) {
                $('#category-modal-error').text((xhr.responseJSON && xhr.responseJSON.error) || 'Failed to save.');
            });
        } else {
            ajax({
                url: '/api/manage/categories/',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ name: name })
            }).done(function (res) {
                $('#category-modal').hide();
                currentCategoryId = res.id;
                loadCategories();
            }).fail(function (xhr) {
                $('#category-modal-error').text((xhr.responseJSON && xhr.responseJSON.error) || 'Failed to save.');
            });
        }
    });

    function toggleCategoryActive(cat) {
        ajax({
            url: '/api/manage/categories/' + cat.id + '/',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ is_active: !cat.is_active })
        }).done(loadCategories);
    }

    function deleteCategory(cat) {
        if (!confirm('Delete category "' + cat.name + '" and all its items? This cannot be undone.')) return;
        ajax({ url: '/api/manage/categories/' + cat.id + '/', method: 'DELETE' }).done(function () {
            if (currentCategoryId === cat.id) currentCategoryId = null;
            loadCategories();
        });
    }

    /* ---------- Item modal ---------- */
    function addVariantRow(variant) {
        var $row = $('<div class="variant-row"></div>');
        var $name = $('<input type="text" placeholder="Variant name (e.g. Full)">').val(variant ? variant.name : '');
        var $price = $('<input type="number" min="0" step="0.01" placeholder="Price">').val(variant ? variant.price : '');
        var $remove = $('<span class="remove-variant">✕</span>').on('click', function () {
            $row.remove();
        });
        if (variant && variant.id) $row.data('variant-id', variant.id);
        $row.append($name, $price, $remove);
        $('#variant-rows').append($row);
    }

    function openItemModal(item) {
        editingItemId = item ? item.id : null;
        $('#item-modal-title').text(item ? 'Edit Item' : 'Add Item');
        $('#item-name-input').val(item ? item.name : '');
        $('#item-description-input').val(item ? item.description : '');
        $('#item-available-input').prop('checked', item ? item.is_available : true);
        $('#item-image-input').val('');
        $('#variant-rows').empty();

        if (item && item.image_url) {
            $('#item-image-preview').attr('src', item.image_url).show();
        } else {
            $('#item-image-preview').hide();
        }

        if (item && item.variants.length) {
            item.variants.forEach(addVariantRow);
        } else {
            addVariantRow(null);
        }

        $('#item-delete-btn').toggle(!!item);
        $('#item-modal-error').text('');
        $('#item-modal').css('display', 'flex').data('item', item || null);
    }

    $('#add-item-btn').on('click', function () {
        if (!currentCategoryId) return;
        openItemModal(null);
    });

    $('#item-cancel-btn').on('click', function () { $('#item-modal').hide(); });

    $('#add-variant-row-btn').on('click', function () { addVariantRow(null); });

    $('#item-image-input').on('change', function (e) {
        var file = e.target.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function (ev) {
            $('#item-image-preview').attr('src', ev.target.result).show();
        };
        reader.readAsDataURL(file);
    });

    function collectVariants() {
        var variants = [];
        var valid = true;
        $('#variant-rows .variant-row').each(function () {
            var $row = $(this);
            var name = $row.find('input[type="text"]').val().trim() || 'Regular';
            var price = $row.find('input[type="number"]').val();
            if (price === '' || isNaN(price) || parseFloat(price) < 0) {
                valid = false;
                return;
            }
            var v = { name: name, price: parseFloat(price) };
            var vid = $row.data('variant-id');
            if (vid) v.id = vid;
            variants.push(v);
        });
        if (!valid || !variants.length) return null;
        return variants;
    }

    $('#item-save-btn').on('click', function () {
        var name = $('#item-name-input').val().trim();
        if (!name) {
            $('#item-modal-error').text('Item name is required.');
            return;
        }
        var variants = collectVariants();
        if (!variants) {
            $('#item-modal-error').text('Each variant needs a name and a valid price (0 or more).');
            return;
        }

        var formData = new FormData();
        formData.append('name', name);
        formData.append('description', $('#item-description-input').val());
        formData.append('category_id', currentCategoryId);
        formData.append('is_available', $('#item-available-input').is(':checked'));
        formData.append('variants', JSON.stringify(variants));
        var file = $('#item-image-input')[0].files[0];
        if (file) formData.append('image', file);

        var url = editingItemId ? '/api/manage/items/' + editingItemId + '/' : '/api/manage/items/';

        ajax({
            url: url,
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false
        }).done(function () {
            $('#item-modal').hide();
            loadCategories();
        }).fail(function (xhr) {
            $('#item-modal-error').text((xhr.responseJSON && xhr.responseJSON.error) || 'Failed to save item.');
        });
    });

    $('#item-delete-btn').on('click', function () {
        if (!editingItemId) return;
        if (!confirm('Delete this item permanently?')) return;
        ajax({ url: '/api/manage/items/' + editingItemId + '/', method: 'DELETE' }).done(function () {
            $('#item-modal').hide();
            loadCategories();
        });
    });

    // Manage Menu is an admin/setup function, not core order-taking — it's
    // explicitly out of scope for offline support (multipart image uploads
    // don't fit the JSON sync-queue model the rest of this app uses). Block
    // the UI outright rather than let edits silently fail or get lost.
    function applyOfflineGuard() {
        var offline = !navigator.onLine;
        $('#manage-offline-notice').toggle(offline);
        $('#manage-layout-wrapper').toggle(!offline);
        return offline;
    }
    window.addEventListener('online', function () {
        if (!applyOfflineGuard()) loadCategories();
    });
    window.addEventListener('offline', applyOfflineGuard);

    if (!applyOfflineGuard()) {
        loadCategories();
    }
});
