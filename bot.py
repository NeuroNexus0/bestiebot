import random
import os
from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# Initialize bot client
app = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Replace this with your bestie's user ID (you can get it using /id command)
BESTIE_USER_ID = 5672706639

# Quotes list
quotes = [
    "You're not just a star, you're my whole sky. ✨",
    "Your smile makes my day every time 😊",
    "You're the kindest soul I’ve ever met 💖",
    "Just a reminder: You’re amazing. No doubt. 💫"
]

# Photo directory
photo_folder = "photos"
photo_files = [
    os.path.join(photo_folder, f)
    for f in os.listdir(photo_folder)
    if f.lower().endswith(('.jpg', '.jpeg', '.png'))
]

# Song directory
song_folder = "songs"
song_files = [
    os.path.join(song_folder, f)
    for f in os.listdir(song_folder)
    if f.lower().endswith(('.mp3', '.wav', '.m4a'))
]

# Commands
@app.on_message(filters.command("start"))
def start_handler(client, message):
    message.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nTry these commands:\n"
        "/quote – for a sweet message 💬\n"
        "/photo or /vibe – for a surprise picture 📸\n"
        "/music – for a random vibe 🎶\n"
        "/id – to get your user ID 🔍"
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

@app.on_message(filters.command("id"))
def id_handler(client, message):
    message.reply_text(f"Your user ID is: `{message.from_user.id}`", quote=True)

# Scheduler functions
def send_good_morning():
    app.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

def send_good_night():
    app.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

# Start the scheduler
scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))
scheduler.add_job(send_good_morning, trigger='cron', hour=7, minute=30)  # 7:30 AM IST
scheduler.add_job(send_good_night, trigger='cron', hour=22, minute=0)    # 10:00 PM IST
scheduler.start()

# Run the bot
app.run()
