import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
PAYMENT_CARD = os.getenv('PAYMENT_CARD', '8600 0000 0000 0000')
CARD_HOLDER = os.getenv('CARD_HOLDER', 'CARD HOLDER')
FREE_DAILY_LIMIT = int(os.getenv('FREE_DAILY_LIMIT', '3'))
REFERRAL_BONUS = int(os.getenv('REFERRAL_BONUS', '3'))
WEB_BASE_URL = os.getenv('WEB_BASE_URL', 'https://your-domain.com')
LOG_GROUP_ID = int(os.getenv('LOG_GROUP_ID', '0'))

# Required channels for forced subscription
_channels = os.getenv('REQUIRED_CHANNELS', '')
REQUIRED_CHANNELS = [ch.strip() for ch in _channels.split(',') if ch.strip()]

# Subscription prices
PRICES = {
    '10_limit': {'amount': 5000, 'limits': 10, 'name': '10 ta limit'},
    '30_limit': {'amount': 10000, 'limits': 30, 'name': '30 ta limit'},
    '100_limit': {'amount': 25000, 'limits': 100, 'name': '100 ta limit'},
    'unlimited': {'amount': 50000, 'limits': 999, 'name': 'Cheksiz (1 oy)'},
}

# Prank types
PRANK_TYPES = {
    'virus': '🦠 Fake Virus',
    'hack': '💀 Fake Hack',
    'jumpscare': '👻 Jumpscare',
    'crash': '📱 Fake Crash',
    'download': '📥 Fake Data Download',
    'wifi': '📡 Fake WiFi Hack',
    'rickroll': '🎵 Rickroll Trap',
}

# Phishing prank types (fake login pages)
PHISHING_TYPES = {
    'instagram': '📸 Instagram',
    'twitter': '🐦 Twitter',
    'twitch': '🎮 Twitch',
    'tiktok': '🎵 TikTok',
    'google': '🔍 Google',
    'telegram': '✈️ Telegram',
    'facebook': '📘 Facebook',
    'vk': '💙 VKontakte',
}

# Image effect types
IMAGE_EFFECTS = {
    'glitch': '🔴 Glitch Effect',
    'matrix': '💚 Matrix Effect',
    'hacker': '🖥 Hacker Style',
    'pixel': '🟩 Pixelate',
    'negative': '🔄 Negative',
    'red_alert': '🔴 Red Alert',
    'ghost': '👻 Ghost Effect',
    'spy': '🕵️ Spy Camera',
}
