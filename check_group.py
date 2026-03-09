import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

async def check():
    bot_token = os.getenv('BOT_TOKEN')
    group_id = os.getenv('LOG_GROUP_ID')
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://api.telegram.org/bot{bot_token}/getMe") as r:
            print("Bot Info:", await r.text())
        print(f"Checking group_id: {group_id}")
        url = f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={group_id}"
        async with s.get(url) as r:
            print("Group Status:", await r.text())

if __name__ == "__main__":
    asyncio.run(check())
