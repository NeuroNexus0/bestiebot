# bot.py
import random
import os
from pyrogram import Client, filters
from config import api_id, api_hash, bot_token

# Initialize bot client
app = Client("bestie_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

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

# Start command
@app.on_message(filters.command("start"))
def start_handler(client, message):
    message.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nTry these commands:\n"
        "/quote – for a sweet message 💬\n"
        "/photo or /vibe – for a surprise picture 📸\n"
        "/music – for a random vibe 🎶"
    )

# Quote command
@app.on_message(filters.command("quote"))
def quote_handler(client, message):
    message.reply_text(random.choice(quotes))

# Photo/vibe command
@app.on_message(filters.command(["photo", "vibe"]))
def photo_handler(client, message):
    if photo_files:
        message.reply_photo(photo=random.choice(photo_files))
    else:
        message.reply_text("Oops, no photos found!")

# Music command
@app.on_message(filters.command("music"))
def music_handler(client, message):
    if song_files:
        message.reply_audio(audio=random.choice(song_files), caption="Here's a vibe for you 🎧")
    else:
        message.reply_text("Oops, no songs found!")

# Run the bot
app.run()


