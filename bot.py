import os
from fastapi import FastAPI, Request
from pyrogram import Client
from pyrogram.types import Update
import random

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.onrender.com

app = FastAPI()
bot = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

quotes = [
    "You're not just a star, you're my whole sky. ✨",
    "Your smile makes my day every time 😊",
    "You're the kindest soul I’ve ever met 💖",
    "Just a reminder: You’re amazing. No doubt. 💫"
]

@app.on_event("startup")
async def startup():
    await bot.start()
    # Set webhook to point Telegram to our FastAPI endpoint
    await bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")

@app.on_event("shutdown")
async def shutdown():
    await bot.stop()

@app.post(f"/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    json_update = await request.json()
    update = Update.de_json(json_update)
    await bot.process_new_updates([update])
    return {"status": "ok"}

# Handlers

@bot.on_message()
async def handle_message(client, message):
    if message.text:
        cmd = message.text.lower()
        if cmd == "/start":
            await message.reply("Hey Bestie! Use /quote for a sweet message.")
        elif cmd == "/quote":
            await message.reply(random.choice(quotes))
        else:
            await message.reply("Unknown command. Try /start or /quote.")
