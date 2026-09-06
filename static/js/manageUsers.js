$(function () {
    var users = [];
    var editingUserId = null;

    function ajax(opts) {
        opts.headers = opts.headers || {};
        opts.headers['X-CSRFToken'] = window.CSRF_TOKEN;
        return $.ajax(opts);
    }

    function loadUsers() {
        ajax({ url: '/api/users/', method: 'GET' }).done(function (res) {
            users = res.users;
            renderUsersTable();
        });
    }

    function renderUsersTable() {
        var $body = $('#users-body').empty();
        if (!users.length) {
            $body.append('<tr><td colspan="5" style="color:#888">No users found.</td></tr>');
            return;
        }
        users.forEach(function (user) {
            var $row = $('<tr></tr>');
            $row.append($('<td></td>').text(user.username + (user.is_self ? ' (you)' : '')));
            $row.append($('<td></td>').text(user.role_display));
            var $statusTd = $('<td></td>');
            var badgeClass = user.is_active ? 'completed' : 'cancelled';
            var badgeLabel = user.is_active ? 'Active' : 'Disabled';
            $statusTd.append($('<span class="status-badge"></span>').addClass(badgeClass).text(badgeLabel));
            $row.append($statusTd);
            $row.append($('<td></td>').text(user.date_joined));
            var $actionTd = $('<td></td>');
            if (!user.is_self) {
                var $editBtn = $('<button type="button" class="link-btn">Edit</button>').on('click', function () {
                    openUserModal(user);
                });
                $actionTd.append($editBtn);
            }
            $row.append($actionTd);
            $body.append($row);
        });
    }

    function openUserModal(user) {
        editingUserId = user ? user.id : null;
        $('#user-modal-title').text(user ? 'Edit User' : 'Add User');
        $('#user-username-input').val(user ? user.username : '').prop('disabled', !!user);
        $('#user-password-input').val('').attr('placeholder', user ? 'Leave blank to keep current password' : 'At least 8 characters');
        $('#user-password-label').text(user ? 'New Password (optional)' : 'Password');
        $('#user-role-input').val(user ? user.role : 'cashier');
        $('#user-active-row').toggle(!!user);
        $('#user-active-input').prop('checked', user ? user.is_active : true);
        $('#user-delete-btn').toggle(!!user);
        $('#user-modal-error').text('');
        $('#user-modal').css('display', 'flex');
        $('#user-username-input').focus();
    }

    $('#add-user-btn').on('click', function () { openUserModal(null); });
    $('#user-cancel-btn, #user-close-x').on('click', function () { $('#user-modal').hide(); });

    $('#user-save-btn').on('click', function () {
        var username = $('#user-username-input').val().trim();
        var password = $('#user-password-input').val();
        var role = $('#user-role-input').val();
        $('#user-modal-error').text('');

        if (editingUserId) {
            var payload = { role: role, is_active: $('#user-active-input').is(':checked') };
            if (password) payload.password = password;
            ajax({
                url: '/api/users/' + editingUserId + '/',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify(payload)
            }).done(function () {
                $('#user-modal').hide();
                loadUsers();
            }).fail(function (xhr) {
                $('#user-modal-error').text((xhr.responseJSON && xhr.responseJSON.error) || 'Failed to save.');
            });
        } else {
            if (!username) {
                $('#user-modal-error').text('Username is required.');
                return;
            }
            ajax({
                url: '/api/users/',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ username: username, password: password, role: role })
            }).done(function () {
                $('#user-modal').hide();
                loadUsers();
            }).fail(function (xhr) {
                $('#user-modal-error').text((xhr.responseJSON && xhr.responseJSON.error) || 'Failed to save.');
            });
        }
    });

    $('#user-delete-btn').on('click', function () {
        if (!editingUserId) return;
        var user = users.find(function (u) { return u.id === editingUserId; });
        if (!confirm('Delete user "' + (user ? user.username : '') + '" permanently? This cannot be undone.')) return;
        ajax({ url: '/api/users/' + editingUserId + '/', method: 'DELETE' }).done(function () {
            $('#user-modal').hide();
            loadUsers();
        }).fail(function (xhr) {
            $('#user-modal-error').text((xhr.responseJSON && xhr.responseJSON.error) || 'Failed to delete.');
        });
    });

    loadUsers();
});
