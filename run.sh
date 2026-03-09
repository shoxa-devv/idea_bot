#!/bin/bash

echo "🤖 Prank Bot o'rnatilmoqda..."

# Check if running inside Docker
if [ -f /.dockerenv ]; then
    echo "🐳 Docker konteynerida ishga tushmoqda..."
else
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        echo "📦 Virtual muhit yaratilmoqda..."
        python3 -m venv venv
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Install dependencies
    echo "📥 Kutubxonalar o'rnatilmoqda..."
    pip install -r requirements.txt
fi

# Create .env from example if it doesn't exist
if [ ! -f ".env" ]; then
    if [ ! -f "/app/.env" ]; then
        cp .env.example .env
        echo "⚠️ .env fayli yaratildi. Iltimos, sozlamalarni kiriting!"
        echo "   BOT_TOKEN — @BotFather dan oling"
        echo "   ADMIN_ID — Telegram ID ingiz"
        echo ""
        echo "Sozlagandan keyin qaytadan ishga tushiring: ./run.sh"
        exit 1
    fi
fi

# Run the bot
echo "🚀 Bot ishga tushirilmoqda..."
python3 bot.py
