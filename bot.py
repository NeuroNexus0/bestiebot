import os
from flask import Flask, request
from pyrogram import Client
from pyrogram.types import Update
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import random

# Load from environment
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

# Create Pyrogram Client
app = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
flask_app = Flask(__name__)

BESTIE_USER_ID = 5672706639

# Quotes & files
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

# Handlers
@app.on_message()
def handle_all_messages(client, message):
    if message.text == "/start":
        message.reply_text("Hey Bestie! 💌\n\nTry these:\n/quote\n/photo\n/music\n/ttt\n/id")
    elif message.text == "/quote":
        message.reply_text(random.choice(quotes))
    elif message.text in ["/photo", "/vibe"]:
        if photo_files:
            message.reply_photo(photo=random.choice(photo_files))
        else:
            message.reply_text("Oops, no photos found!")
    elif message.text == "/music":
        if song_files:
            message.reply_audio(audio=random.choice(song_files), caption="Here's a vibe 🎧")
        else:
            message.reply_text("Oops, no songs found!")
    elif message.text == "/id":
        message.reply_text(f"Your user ID is: `{message.from_user.id}`", quote=True)

# Scheduler
def send_good_morning():
    app.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

def send_good_night():
    app.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))
scheduler.add_job(send_good_morning, trigger='cron', hour=7, minute=30)
scheduler.add_job(send_good_night, trigger='cron', hour=22, minute=0)
scheduler.start()

# Flask endpoint for webhook
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def receive_update():
    update = Update.de_json(request.get_json(force=True))
    app.process_update(update)
    return "OK"

# Start everything
if __name__ == "__main__":
    with app:
        app.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        flask_app.run(host="0.0.0.0", port=PORT)
