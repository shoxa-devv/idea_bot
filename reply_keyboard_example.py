from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

# Ozizning bot tokeningizni bu yerga " " ichiga yozing:
TOKEN = "TOKEN_YERI"

# /start komandasi handler-i
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga tugmalarni (keyboard) ko'rsatish."""
    
    # Tugmalar (Keyboard buttons)
    # Jadval korinishida: har bir ichki ro'yxat bitta qatorni bildiradi.
    buttons = [
        [KeyboardButton("🎭 Prank yuborish"), KeyboardButton("🌐 Phishing sayt")],
        [KeyboardButton("👤 Profilim"), KeyboardButton("🔗 Referal")],
        [KeyboardButton("📊 Statistika")],
        [KeyboardButton("ℹ️ Yordam")]
    ]
    
    # ReplyKeyboardMarkup yaratish
    # resize_keyboard=True - tugmalar o'lchamini ekranga moslashtiradi
    # one_time_keyboard=False - tugmalar bosilgandan keyin ham ko'rinib turadi
    # input_field_placeholder - yozish joyida turadigan matn
    reply_markup = ReplyKeyboardMarkup(
        buttons, 
        resize_keyboard=True, 
        one_time_keyboard=False,
        input_field_placeholder="Bo'limni tanlang..."
    )
    
    # Xush kelibsiz xabari va tugmalarni yuborish
    await update.message.reply_text(
        f"Salom, {update.effective_user.first_name}!\n\n"
        f"Botga xush kelibsiz. Quyidagi tugmalardan birini tanlang:",
        reply_markup=reply_markup
    )

# Matnli xabarlarni qayta ishlash handler-i
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi tugmani bosganda keladigan matnni tekshirish."""
    text = update.message.text
    
    if text == "🎭 Prank yuborish":
        await update.message.reply_text("Siz Prank yuborish bo'limini tanladingiz! 🎭")
    elif text == "🌐 Phishing sayt":
        await update.message.reply_text("Siz Phishing sayt yaratish bo'limini tanladingiz! 🌐")
    elif text == "👤 Profilim":
        await update.message.reply_text("Sizning profilingiz ma'lumotlari... 👤")
    elif text == "🔗 Referal":
        await update.message.reply_text("Sizning referal havolangiz... 🔗")
    else:
        # Agar boshqa narsa yozsa
        await update.message.reply_text(f"Siz: '{text}' deb yozdingiz. Iltimos, tugmalardan birini tanlang.")

def main():
    """Botni ishga tushirish."""
    # 1. Application yaratish (Token orqali)
    application = Application.builder().token(TOKEN).build()
    
    # 2. Handlerlarni qo'shish (Buyruqlar va Matnlar uchun)
    # /start buyrug'i uchun
    application.add_handler(CommandHandler("start", start_command))
    
    # Har qanday matn (command bo'lmagan) uchun
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 3. Botni ishga tushirish (Polling - doimiy tekshirib turish)
    print("Bot ishga tushirildi. Telegramda /start bosing.")
    application.run_polling()

if __name__ == "__main__":
    main()
