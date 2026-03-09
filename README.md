# 🤖 Prank Bot

Do'stlaringizga hazil qilish uchun Telegram bot!

## 🎯 Funksiyalar

### 🎭 Prank sahifalar
- 🦠 **Fake Virus** — telefoningiz virusga chalingan ko'rsatadi
- 💀 **Fake Hack** — hacker terminal animatsiyasi
- 👻 **Jumpscare** — qo'rqinchli prank
- 📱 **Fake Crash** — ko'k ekran (BSOD)
- 📥 **Fake Data Download** — ma'lumotlar yuklanmoqda ko'rsatadi
- 📡 **Fake WiFi Hack** — WiFi parollar skanerlanmoqda
- 🎵 **Rickroll** — klassik Rickroll trap

### 🖼 Rasm effektlari (8 ta)
- 🔴 Glitch — buzilish effekti
- 💚 Matrix — Matrix uslubi
- 🖥 Hacker — hacker kameras
- 🟩 Pixel — piksellashtirish
- 🔄 Negative — teskari ranglar
- 🔴 Red Alert — qizil ogohlantirish
- 👻 Ghost — arvoh effekti
- 🕵️ Spy Camera — kuzatuv kamerasi

### 🔗 Referal tizimi
- Har bir do'st = +3 limit
- Ulashish tugmasi

### 💰 To'lov tizimi
- 4 xil paket
- Karta orqali to'lov
- Chek yuborish
- Admin tasdiqlaydi

### 👨‍💼 Admin panel
- Statistika
- Broadcast xabar
- To'lovlarni boshqarish

## 🚀 O'rnatish

1. `.env.example` faylini `.env` ga nusxalang:
```bash
cp .env.example .env
```

2. `.env` faylini sozlang:
```
BOT_TOKEN=your_token_from_botfather
ADMIN_ID=your_telegram_id
PAYMENT_CARD=8600_xxxx_xxxx_xxxx
CARD_HOLDER=YOUR_NAME
WEB_BASE_URL=https://your-domain.com
```

3. Botni ishga tushiring:
```bash
chmod +x run.sh
./run.sh
```

## 📋 Web sahifalar uchun

Prank sahifalari `web_pages/` papkasida joylashgan.
Ularni serverda joylashtirish uchun `web_server.py` faylidan foydalanishingiz yoki
Cloudflare Pages, Netlify kabi xizmatlarga yuklashingiz mumkin.

## 📌 Bot buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/start` | Botni boshlash |
| `/help` | Yordam |
| `/profile` | Profil |
| `/referral` | Referal havola |
| `/buy` | Limit sotib olish |

### Admin buyruqlari
| Buyruq | Tavsif |
|--------|--------|
| `/admin` | Admin panel |
| `/broadcast` | Broadcast xabar |
| `/stats_admin` | To'liq statistika |
| `/pending` | Kutilayotgan to'lovlar |
