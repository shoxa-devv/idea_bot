// Telegram WebApp integration with fallback
let tg = null;
try {
    if (window.Telegram && window.Telegram.WebApp) {
        tg = window.Telegram.WebApp;
        tg.expand();
    }
} catch (e) {
    console.log('Not running in Telegram WebApp context');
}

function showAlert(msg) {
    if (tg && tg.showAlert) {
        try {
            tg.showAlert(msg);
        } catch (e) {
            alert(msg);
        }
    } else {
        alert(msg);
    }
}

// DOM elements
const statsUsers = document.getElementById('stat-total-users');
const statsWins = document.getElementById('stat-total-wins');
const statsReferrals = document.getElementById('stat-total-referrals');

const settingsForm = document.getElementById('settings-form');
const channelForm = document.getElementById('channel-form');
const channelsTableBody = document.getElementById('channels-table-body');
const usersTableBody = document.getElementById('users-table-body');

const broadcastBtn = document.getElementById('btn-broadcast');
const broadcastModal = document.getElementById('broadcast-modal');
const broadcastCloseBtn = document.getElementById('broadcast-close-btn');
const broadcastSendBtn = document.getElementById('broadcast-send-btn');
const broadcastText = document.getElementById('broadcast-text');

// API helpers
async function apiCall(endpoint, method = 'GET', data = null) {
    try {
        const options = {
            method,
            headers: {}
        };

        // Add Telegram auth data if available
        if (tg && tg.initData) {
            options.headers['X-TG-Data'] = tg.initData;
        }

        if (data instanceof FormData) {
            options.body = data;
        } else if (data) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(data);
        }

        const response = await fetch(`/api/admin/${endpoint}`, options);
        if (!response.ok) {
            console.error(`API ${endpoint} returned ${response.status}`);
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        showAlert('Server bilan bog\'lanishda xatolik yuz berdi!');
        return null;
    }
}

// Load Stats
async function loadStats() {
    const data = await apiCall('stats');
    if (data) {
        statsUsers.innerText = data.total_users || 0;
        statsWins.innerText = data.total_pranks_sent || 0;
        statsReferrals.innerText = data.total_referrals || 0;

        // Update broadcast button count
        const btnCount = document.getElementById('btn-count');
        if (btnCount) btnCount.innerText = data.total_users || 0;
    }
}

// Load Settings
async function loadSettings() {
    const data = await apiCall('settings');
    if (data) {
        document.getElementById('setting-admin-pass').value = data.admin_password || '';
        document.getElementById('setting-ref-bonus').value = data.referral_bonus || 3;
        document.getElementById('setting-daily-limit').value = data.daily_limit || 3;
    }
}

// Load Channels
async function loadChannels() {
    const channels = await apiCall('channels');
    if (channels) {
        channelsTableBody.innerHTML = '';
        channels.forEach(ch => {
            const row = document.createElement('tr');
            const channelLink = ch.channel_username.startsWith('https')
                ? ch.channel_username
                : 'https://t.me/' + ch.channel_username.replace('@', '');
            row.innerHTML = `
                <td>${ch.channel_title || 'Nomi yo\'q'}</td>
                <td><code>${ch.channel_username}</code></td>
                <td><a href="${channelLink}" target="_blank" class="link-btn">Kanalga o'tish</a></td>
                <td><button class="btn-red" onclick="deleteChannel('${ch.channel_username}')">O'chirish</button></td>
            `;
            channelsTableBody.appendChild(row);
        });
    }
}

// Load Users
async function loadUsers() {
    const users = await apiCall('users');
    if (users) {
        usersTableBody.innerHTML = '';
        users.slice(0, 50).forEach(u => {
            const row = document.createElement('tr');
            row.className = 'user-row';
            row.innerHTML = `
                <td>#${u.user_id}</td>
                <td><b>${u.first_name || ''}</b><br><small style="color:var(--text-secondary)">@${u.username || 'yo\'q'}</small></td>
                <td><span class="badge badge-purple">${u.total_limits} ta</span></td>
                <td><span class="badge ${u.is_banned ? 'btn-red' : 'badge-blue'}">${u.is_banned ? 'Banned' : 'Active'}</span></td>
                <td>${u.last_reset_date || '-'}</td>
                <td>${u.joined_date ? u.joined_date.substring(0, 10) : '-'}</td>
            `;
            usersTableBody.appendChild(row);
        });
    }
}

// Actions
settingsForm.onsubmit = async (e) => {
    e.preventDefault();
    const data = {
        admin_password: document.getElementById('setting-admin-pass').value,
        referral_bonus: document.getElementById('setting-ref-bonus').value,
        daily_limit: document.getElementById('setting-daily-limit').value
    };
    const res = await apiCall('settings', 'POST', data);
    if (res && res.status === 'ok') {
        showAlert('✅ Sozlamalar muvaffaqiyatli saqlandi!');
    }
};

channelForm.onsubmit = async (e) => {
    e.preventDefault();
    const title = document.getElementById('chan-title').value;
    const username = document.getElementById('chan-id').value;
    const data = {
        title: title,
        username: username
    };
    if (!data.username) {
        showAlert('Username kiriting!');
        return;
    }
    const res = await apiCall('channels', 'POST', data);
    if (res && res.status === 'ok') {
        showAlert('✅ Kanal qo\'shildi!');
        loadChannels();
        channelForm.reset();
    }
};

window.deleteChannel = async (username) => {
    if (confirm('Rostdan ham o\'chirmoqchimisiz?')) {
        const res = await apiCall(`channels?username=${encodeURIComponent(username)}`, 'DELETE');
        if (res && res.status === 'ok') {
            showAlert('✅ Kanal o\'chirildi!');
            loadChannels();
        }
    }
};

// Broadcast
broadcastBtn.onclick = () => {
    broadcastModal.style.display = 'flex';
    document.getElementById('broadcast-progress-container').style.display = 'none';
    document.getElementById('broadcast-done-text').style.display = 'none';
    broadcastText.value = '';
    document.getElementById('broadcast-image').value = '';
    document.getElementById('broadcast-btn-text').value = '';
    document.getElementById('broadcast-btn-url').value = '';
};
broadcastCloseBtn.onclick = () => broadcastModal.style.display = 'none';

broadcastSendBtn.onclick = async () => {
    const text = broadcastText.value.trim();
    const imageFile = document.getElementById('broadcast-image').files[0];
    const btnText = document.getElementById('broadcast-btn-text').value.trim();
    const btnUrl = document.getElementById('broadcast-btn-url').value.trim();

    if (!text) {
        showAlert('Matnni kiriting!');
        return;
    }

    // Reset and show progress UI
    const progressContainer = document.getElementById('broadcast-progress-container');
    const progressBar = document.getElementById('broadcast-progress-bar');
    const statusText = document.getElementById('broadcast-status-text');
    const percentageText = document.getElementById('broadcast-percentage');
    const doneText = document.getElementById('broadcast-done-text');

    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    percentageText.innerText = '0%';
    statusText.innerText = 'Boshlanmoqda...';
    doneText.style.display = 'none';

    broadcastSendBtn.disabled = true;
    const originalBtnText = broadcastSendBtn.innerHTML;
    broadcastSendBtn.innerText = 'Yuborilmoqda...';

    const formData = new FormData();
    formData.append('text', text);
    if (imageFile) formData.append('image', imageFile);
    if (btnText) formData.append('btn_text', btnText);
    if (btnUrl) formData.append('btn_url', btnUrl);

    const res = await apiCall('broadcast', 'POST', formData);

    if (res && res.status === 'ok') {
        const total = res.count;

        // Start polling for status
        const pollInterval = setInterval(async () => {
            try {
                const status = await apiCall('broadcast_status');
                if (status) {
                    const sent = status.sent || 0;
                    const totalCount = status.total || total;
                    const percent = totalCount > 0 ? Math.round((sent / totalCount) * 100) : 0;

                    progressBar.style.width = `${percent}%`;
                    percentageText.innerText = `${percent}%`;
                    statusText.innerText = `Yuborildi: ${sent} / ${totalCount}`;

                    // Stop polling when broadcast is done
                    if (!status.is_running) {
                        clearInterval(pollInterval);
                        broadcastSendBtn.disabled = false;
                        broadcastSendBtn.innerHTML = originalBtnText;
                        doneText.style.display = 'block';
                        statusText.innerText = 'Tayyor!';
                        progressBar.style.width = '100%';
                        percentageText.innerText = '100%';
                    }
                }
            } catch (e) {
                console.error('Poll error:', e);
                clearInterval(pollInterval);
                broadcastSendBtn.disabled = false;
                broadcastSendBtn.innerHTML = originalBtnText;
            }
        }, 1000);
    } else {
        broadcastSendBtn.disabled = false;
        broadcastSendBtn.innerHTML = originalBtnText;
        progressContainer.style.display = 'none';
    }
};

// Initial load
loadStats();
loadSettings();
loadChannels();
loadUsers();
