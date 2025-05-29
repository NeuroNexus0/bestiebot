import os
import random
from pyrogram import Client, filters
from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import httpx
import asyncio

# Load environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Your public URL, e.g. https://yourapp.onrender.com
PORT = int(os.getenv("PORT", 8000))  # default port

# Initialize Pyrogram bot client
bot = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize FastAPI app
app = FastAPI()

# Scheduler for daily messages
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))

BESTIE_USER_ID = 5672706639  # change to your user id or target user id

quotes = [
    "You're not just a star, you're my whole sky. ✨",
    "Your smile makes my day every time 😊",
    "You're the kindest soul I’ve ever met 💖",
    "Just a reminder: You’re amazing. No doubt. 💫"
]

photo_folder = "photos"
photo_files = [os.path.join(photo_folder, f) for f in os.listdir(photo_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

song_folder = "songs"
song_files = [os.path.join(song_folder, f) for f in os.listdir(song_folder) if f.lower().endswith(('.mp3', '.wav', '.m4a'))]

# Telegram commands handlers
@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nTry these commands:\n"
        "/quote – for a sweet message 💬\n"
        "/photo or /vibe – for a surprise picture 📸\n"
        "/music – for a random vibe 🎶\n"
        "/id – to get your user ID 🔍\n"
        "/ttt – play Tic Tac Toe 🎮"
    )

@bot.on_message(filters.command("quote"))
async def quote_handler(client, message):
    await message.reply_text(random.choice(quotes))

@bot.on_message(filters.command(["photo", "vibe"]))
async def photo_handler(client, message):
    if photo_files:
        await message.reply_photo(photo=random.choice(photo_files))
    else:
        await message.reply_text("Oops, no photos found!")

@bot.on_message(filters.command("music"))
async def music_handler(client, message):
    if song_files:
        await message.reply_audio(audio=random.choice(song_files), caption="Here's a vibe for you 🎧")
    else:
        await message.reply_text("Oops, no songs found!")

@bot.on_message(filters.command("id"))
async def id_handler(client, message):
    await message.reply_text(f"Your user ID is: `{message.from_user.id}`", quote=True)

# Daily scheduled messages
async def send_good_morning():
    await bot.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

async def send_good_night():
    await bot.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

scheduler.add_job(send_good_morning, trigger='cron', hour=7, minute=30)
scheduler.add_job(send_good_night, trigger='cron', hour=22, minute=0)

# Tic Tac Toe game logic omitted for brevity — add as needed

# Webhook endpoint for Telegram updates
@app.post(f"/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    update = await request.json()
    await bot.process_update(update)
    return PlainTextResponse("ok")

# Root endpoint (optional)
@app.get("/")
async def root():
    return {"message": "Bestie Bot is running!"}

# Startup event: start bot & scheduler, set webhook
@app.on_event("startup")
async def startup_event():
    await bot.start()
    scheduler.start()
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    set_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    async with httpx.AsyncClient() as client:
        response = await client.post(set_webhook_url, data={"url": webhook_url})
        print("Webhook set response:", response.json())

# Shutdown event: stop bot and scheduler
@app.on_event("shutdown")
async def shutdown_event():
    await bot.stop()
    scheduler.shutdown()

# Run via uvicorn if executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
