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

# --- Tic Tac Toe game logic ---

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Game states stored per user (user_id -> game state)
games = {}

def render_board_text(board):
    # Map symbols to emojis with colors:
    symbol_map = {
        "X": "❌",  # red cross mark
        "O": "⚫",  # black circle
        " ": "⬜"   # white square for empty
    }

    rows = []
    for i in range(3):
        row_symbols = [symbol_map[board[j + i*3]] for j in range(3)]
        row_text = " | ".join(row_symbols)
        rows.append(row_text)

    board_text = "\n---------\n".join(rows)
    return board_text

def check_winner(board, player):
    wins = [
        [0,1,2], [3,4,5], [6,7,8],  # rows
        [0,3,6], [1,4,7], [2,5,8],  # cols
        [0,4,8], [2,4,6]            # diagonals
    ]
    for line in wins:
        if all(board[pos] == player for pos in line):
            return True
    return False

def is_board_full(board):
    return all(space != " " for space in board)

def get_available_moves(board):
    return [i for i, spot in enumerate(board) if spot == " "]

# Minimax for tough bot AI playing O
def minimax(board, depth, is_maximizing):
    if check_winner(board, "O"):
        return 10 - depth
    if check_winner(board, "X"):
        return depth - 10
    if is_board_full(board):
        return 0

    if is_maximizing:
        best_score = -float('inf')
        for move in get_available_moves(board):
            board[move] = "O"
            score = minimax(board, depth + 1, False)
            board[move] = " "
            best_score = max(score, best_score)
        return best_score
    else:
        best_score = float('inf')
        for move in get_available_moves(board):
            board[move] = "X"
            score = minimax(board, depth + 1, True)
            board[move] = " "
            best_score = min(score, best_score)
        return best_score

def bot_move(board):
    best_score = -float('inf')
    best_move = None
    for move in get_available_moves(board):
        board[move] = "O"
        score = minimax(board, 0, False)
        board[move] = " "
        if score > best_score:
            best_score = score
            best_move = move
    return best_move

def build_board_keyboard(board):
    keyboard = []
    for row in range(3):
        buttons = []
        for col in range(3):
            idx = row * 3 + col
            if board[idx] == " ":
                buttons.append(InlineKeyboardButton(str(idx+1), callback_data=f"ttt_{idx}"))
            else:
                # Show emoji, no callback
                symbol_map = {"X": "❌", "O": "⚫"}
                buttons.append(InlineKeyboardButton(symbol_map[board[idx]], callback_data="noop"))
        keyboard.append(buttons)
    return InlineKeyboardMarkup(keyboard)

async def start_game(user_id):
    board = [" "] * 9
    games[user_id] = board
    text = "Your turn! You're ❌ (X).\n\n" + render_board_text(board)
    markup = build_board_keyboard(board)
    return text, markup

async def handle_move(user_id, idx):
    board = games.get(user_id)
    if board is None:
        return None, None, "No game in progress. Send /ttt to start."

    if board[idx] != " ":
        return None, None, "Invalid move! This cell is already taken."

    # Player move
    board[idx] = "X"
    if check_winner(board, "X"):
        text = render_board_text(board) + "\n\nYou won! 🎉 Send /ttt to play again."
        games.pop(user_id)
        return text, None, None
    elif is_board_full(board):
        text = render_board_text(board) + "\n\nIt's a draw! Send /ttt to try again."
        games.pop(user_id)
        return text, None, None

    # Bot move
    bot_idx = bot_move(board)
    if bot_idx is not None:
        board[bot_idx] = "O"

    if check_winner(board, "O"):
        text = render_board_text(board) + "\n\nI won! Better luck next time 😎 Send /ttt to play again."
        games.pop(user_id)
        return text, None, None
    elif is_board_full(board):
        text = render_board_text(board) + "\n\nIt's a draw! Send /ttt to try again."
        games.pop(user_id)
        return text, None, None

    # Game continues
    text = "Your turn! You're ❌ (X).\n\n" + render_board_text(board)
    markup = build_board_keyboard(board)
    return text, markup, None

# --- Telegram commands handlers ---

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

# Start Tic Tac Toe game
@bot.on_message(filters.command("ttt"))
async def ttt_handler(client, message):
    user_id = message.from_user.id
    text, markup = await start_game(user_id)
    await message.reply_text(text, reply_markup=markup)

# Handle callback queries (button presses) for Tic Tac Toe moves
@bot.on_callback_query(filters.regex(r"ttt_\d"))
async def ttt_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data  # format: ttt_0 .. ttt_8
    idx = int(data.split("_")[1])

    text, markup, error = await handle_move(user_id, idx)
    if error:
        await callback_query.answer(error, show_alert=True)
        return

    # Edit the original message with updated board
    await callback_query.message.edit_text(text, reply_markup=markup)
    await callback_query.answer()

@bot.on_callback_query(filters.regex("noop"))
async def noop_handler(client, callback_query):
    # Just answer silently for disabled buttons
    await callback_query.answer()

# --- Daily scheduled messages ---

async def send_good_morning():
    await bot.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

async def send_good_night():
    await bot.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

scheduler.add_job(send_good_morning, trigger='cron', hour=7, minute=30)
scheduler.add_job(send_good_night, trigger='cron', hour=22, minute=0)

# --- Webhook endpoint for Telegram updates ---

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
