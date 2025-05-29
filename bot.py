<<<<<<< HEAD
=======

>>>>>>> e36cd8e (UPDATE)
import random
import os
from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN
<<<<<<< HEAD

# Initialize bot client
app = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
=======
import uvicorn
from fastapi import FastAPI, Request

# Initialize bot client
app = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# FastAPI server for Render
server = FastAPI()
>>>>>>> e36cd8e (UPDATE)

# Quotes list
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

@app.on_message(filters.command("start"))
def start_handler(client, message):
    message.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nTry these commands:\n"
        "/quote – for a sweet message 💬\n"
        "/photo or /vibe – for a surprise picture 📸\n"
        "/music – for a random vibe 🎶"
    )

@app.on_message(filters.command("quote"))
def quote_handler(client, message):
    message.reply_text(random.choice(quotes))

@app.on_message(filters.command(["photo", "vibe"]))
def photo_handler(client, message):
    if photo_files:
        message.reply_photo(photo=random.choice(photo_files))
    else:
        message.reply_text("Oops, no photos found!")

@app.on_message(filters.command("music"))
def music_handler(client, message):
    if song_files:
        message.reply_audio(audio=random.choice(song_files), caption="Here's a vibe for you 🎧")
    else:
        message.reply_text("Oops, no songs found!")

<<<<<<< HEAD
# Run the bot
app.run()
=======
# Start Pyrogram in webhook mode
@server.on_event("startup")
async def startup():
    await app.start()
    await app.set_webhook(url=os.environ["RENDER_EXTERNAL_URL"])

@server.on_event("shutdown")
async def shutdown():
    await app.stop()

@server.post("/")
async def telegram_webhook(request: Request):
    await app.process_update(await request.body())
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("bot:server", host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

>>>>>>> e36cd8e (UPDATE)
