import os
import random
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import httpx

# Load environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://yourapp.onrender.com
PORT = int(os.getenv("PORT", 8000))

# Initialize Pyrogram bot
bot = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# FastAPI app
app = FastAPI()

# APScheduler setup
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))

# Bestie user
BESTIE_USER_ID = 5672706639  # Change to your user ID

# Quote, photo, and music data
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

# --- Tic Tac Toe logic ---
games = {}

def render_board_text(board):
    symbols = {"X": "❌", "O": "⚫", " ": "⬜"}
    rows = []
    for i in range(3):
        row = [symbols[board[j + i * 3]] for j in range(3)]
        rows.append(" | ".join(row))
    return "\n---------\n".join(rows)

def check_winner(board, player):
    wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    return any(all(board[i] == player for i in line) for line in wins)

def is_board_full(board):
    return all(space != " " for space in board)

def get_available_moves(board):
    return [i for i, spot in enumerate(board) if spot == " "]

def minimax(board, depth, is_max):
    if check_winner(board, "O"):
        return 10 - depth
    if check_winner(board, "X"):
        return depth - 10
    if is_board_full(board):
        return 0

    if is_max:
        best = -float("inf")
        for move in get_available_moves(board):
            board[move] = "O"
            score = minimax(board, depth + 1, False)
            board[move] = " "
            best = max(score, best)
        return best
    else:
        best = float("inf")
        for move in get_available_moves(board):
            board[move] = "X"
            score = minimax(board, depth + 1, True)
            board[move] = " "
            best = min(score, best)
        return best

def bot_move(board):
    best_score = -float("inf")
    move = None
    for m in get_available_moves(board):
        board[m] = "O"
        score = minimax(board, 0, False)
        board[m] = " "
        if score > best_score:
            best_score = score
            move = m
    return move

def build_board_keyboard(board):
    kb = []
    for row in range(3):
        btn_row = []
        for col in range(3):
            idx = row * 3 + col
            if board[idx] == " ":
                btn_row.append(InlineKeyboardButton(str(idx+1), callback_data=f"ttt_{idx}"))
            else:
                symbol = {"X": "❌", "O": "⚫"}[board[idx]]
                btn_row.append(InlineKeyboardButton(symbol, callback_data="noop"))
        kb.append(btn_row)
    return InlineKeyboardMarkup(kb)

async def start_game(user_id):
    board = [" "] * 9
    games[user_id] = board
    return "Your turn! You're ❌ (X).\n\n" + render_board_text(board), build_board_keyboard(board)

async def handle_move(user_id, idx):
    board = games.get(user_id)
    if not board:
        return None, None, "No game in progress. Send /ttt to start."
    if board[idx] != " ":
        return None, None, "Invalid move!"

    board[idx] = "X"
    if check_winner(board, "X"):
        del games[user_id]
        return render_board_text(board) + "\n\nYou won! 🎉", None, None
    if is_board_full(board):
        del games[user_id]
        return render_board_text(board) + "\n\nIt's a draw!", None, None

    bot_idx = bot_move(board)
    if bot_idx is not None:
        board[bot_idx] = "O"

    if check_winner(board, "O"):
        del games[user_id]
        return render_board_text(board) + "\n\nI won! 😎", None, None
    if is_board_full(board):
        del games[user_id]
        return render_board_text(board) + "\n\nIt's a draw!", None, None

    return "Your turn! You're ❌ (X).\n\n" + render_board_text(board), build_board_keyboard(board), None

# --- Telegram Handlers ---

@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nTry these commands:\n"
        "/quote – for a sweet message 💬\n"
        "/photo or /vibe – for a surprise picture 📸\n"
        "/music – for a random vibe 🎶\n"
        "/id – to get your user ID 🔍\n"
        "/ttt – play Tic Tac Toe 🎮"
    )

@bot.on_message(filters.command("quote"))
async def quote(client, message):
    await message.reply_text(random.choice(quotes))

@bot.on_message(filters.command(["photo", "vibe"]))
async def photo(client, message):
    if photo_files:
        await message.reply_photo(photo=random.choice(photo_files))
    else:
        await message.reply_text("No photos found!")

@bot.on_message(filters.command("music"))
async def music(client, message):
    if song_files:
        await message.reply_audio(audio=random.choice(song_files), caption="Here's a vibe 🎧")
    else:
        await message.reply_text("No songs found!")

@bot.on_message(filters.command("id"))
async def get_id(client, message):
    await message.reply_text(f"Your user ID is: `{message.from_user.id}`", quote=True)

@bot.on_message(filters.command("ttt"))
async def ttt(client, message):
    user_id = message.from_user.id
    text, markup = await start_game(user_id)
    await message.reply_text(text, reply_markup=markup)

@bot.on_callback_query(filters.regex(r"ttt_\d"))
async def move(client, callback):
    user_id = callback.from_user.id
    idx = int(callback.data.split("_")[1])
    text, markup, error = await handle_move(user_id, idx)
    if error:
        await callback.answer(error, show_alert=True)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
        await callback.answer()

@bot.on_callback_query(filters.regex("noop"))
async def noop(client, callback):
    await callback.answer()

# --- Daily Scheduled Messages ---

async def send_good_morning():
    await bot.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

async def send_good_night():
    await bot.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

scheduler.add_job(send_good_morning, "cron", hour=7, minute=30)
scheduler.add_job(send_good_night, "cron", hour=22, minute=0)

# --- Webhook ---

@app.post(f"/{BOT_TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot.session)
    await bot.dispatcher.feed_update(bot, update)
    return PlainTextResponse("ok")

@app.get("/")
async def root():
    return {"message": "BestieBot is running!"}

@app.on_event("startup")
async def on_startup():
    await bot.start()
    scheduler.start()
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    async with httpx.AsyncClient() as client:
        res = await client.post(api_url, data={"url": webhook_url})
        print("Set webhook:", res.json())

@app.on_event("shutdown")
async def on_shutdown():
    await bot.stop()
    scheduler.shutdown()

# --- Run Server ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
