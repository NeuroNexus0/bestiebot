import random
import os
from pyrogram import Client, filters
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# Load from environment
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Example: https://your-render-url.onrender.com
PORT = int(os.environ.get("PORT", 10000))

# Initialize Pyrogram client
app = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

BESTIE_USER_ID = 5672706639  # Change to your target Telegram user ID

# Quotes, files
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
        "/music – for a random vibe 🎶\n"
        "/id – to get your user ID 🔍\n"
        "/ttt – play Tic Tac Toe 🎮"
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

# Scheduler messages
def send_good_morning():
    app.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

def send_good_night():
    app.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))
scheduler.add_job(send_good_morning, trigger='cron', hour=7, minute=30)
scheduler.add_job(send_good_night, trigger='cron', hour=22, minute=0)
scheduler.start()

# Tic Tac Toe
games = {}

def render_board(board):
    symbols = {'X': '❌', 'O': '⭕', '': '⬜'}
    return '\n'.join(' '.join(symbols[cell] for cell in row) for row in board)

def check_winner(board):
    lines = board + list(zip(*board)) + [[board[i][i] for i in range(3)], [board[i][2 - i] for i in range(3)]]
    for line in lines:
        if line.count(line[0]) == 3 and line[0] != '':
            return line[0]
    return None

def bot_move(board):
    empty = [(r, c) for r in range(3) for c in range(3) if board[r][c] == '']
    return random.choice(empty) if empty else None

@app.on_message(filters.command("ttt"))
def ttt_start(client, message):
    user_id = message.from_user.id
    games[user_id] = {'board': [[''] * 3 for _ in range(3)], 'turn': 'X'}
    message.reply_text("🎮 Let's play Tic Tac Toe!\nJust send a number from 1-9 to make a move.\n\n" +
                       render_board(games[user_id]['board']), quote=True)

@app.on_message(filters.text & filters.private)
def ttt_play(client, message):
    user_id = message.from_user.id
    if user_id not in games or not message.text.isdigit():
        return

    move = int(message.text)
    if not 1 <= move <= 9:
        return message.reply_text("Choose a number between 1 and 9 only!")

    row = (move - 1) // 3
    col = (move - 1) % 3
    game = games[user_id]
    board = game['board']

    if board[row][col] != '':
        return message.reply_text("That spot is already taken!")

    board[row][col] = 'X'
    winner = check_winner(board)
    if winner:
        message.reply_text(render_board(board) + f"\n\n🎉 You win!", quote=True)
        del games[user_id]
        return

    if all(cell for row in board for cell in row):
        message.reply_text(render_board(board) + "\n\n🤝 It's a draw!", quote=True)
        del games[user_id]
        return

    br, bc = bot_move(board)
    board[br][bc] = 'O'
    winner = check_winner(board)

    if winner:
        message.reply_text(render_board(board) + f"\n\n💀 Bot wins!", quote=True)
        del games[user_id]
    elif all(cell for row in board for cell in row):
        message.reply_text(render_board(board) + "\n\n🤝 It's a draw!", quote=True)
        del games[user_id]
    else:
        message.reply_text(render_board(board) + "\n\nYour turn! Send 1-9", quote=True)

# --- Start the bot with webhook ---
if __name__ == "__main__":
    app.run(
        webhook=True,
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )
