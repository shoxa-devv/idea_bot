import asyncio
from database import init_db, create_phishing_token

async def run():
    await init_db()
    t = await create_phishing_token(1897652450, 'instagram')
    print(t)

if __name__ == "__main__":
    asyncio.run(run())
