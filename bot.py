import os
import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import httpx
import asyncio
import copy

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

# --------------------------
# Tic Tac Toe Game Logic
# --------------------------

user_games = {}  # store user_id -> game state dict

def empty_board():
    return [" "] * 9

def render_board_text(board):
    # Show board as text with numbers for empty cells
    def cell_text(i):
        return board[i] if board[i] != " " else str(i+1)
    rows = []
    for i in range(3):
        row = " | ".join(cell_text(j + i*3) for j in range(3))
        rows.append(row)
    return "\n---------\n".join(rows)

def check_winner(board):
    wins = [
        [0,1,2],[3,4,5],[6,7,8],
        [0,3,6],[1,4,7],[2,5,8],
        [0,4,8],[2,4,6]
    ]
    for line in wins:
        if board[line[0]] != " " and board[line[0]] == board[line[1]] == board[line[2]]:
            return board[line[0]]  # 'X' or 'O'
    if " " not in board:
        return "Draw"
    return None

def minimax(board, is_maximizing):
    winner = check_winner(board)
    if winner == "O":  # bot wins
        return 1
    elif winner == "X":  # user wins
        return -1
    elif winner == "Draw":
        return 0

    if is_maximizing:
        best_score = -float("inf")
        for i in range(9):
            if board[i] == " ":
                board[i] = "O"
                score = minimax(board, False)
                board[i] = " "
                best_score = max(score, best_score)
        return best_score
    else:
        best_score = float("inf")
        for i in range(9):
            if board[i] == " ":
                board[i] = "X"
                score = minimax(board, True)
                board[i] = " "
                best_score = min(score, best_score)
        return best_score

def bot_move_minimax(board):
    best_score = -float("inf")
    best_move = None
    for i in range(9):
        if board[i] == " ":
            board[i] = "O"
            score = minimax(board, False)
            board[i] = " "
            if score > best_score:
                best_score = score
                best_move = i
    if best_move is not None:
        board[best_move] = "O"
    return board

def build_board_markup(board):
    buttons = []
    for i in range(9):
        text = board[i] if board[i] != " " else str(i+1)
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"ttt_{i}"))
    keyboard = [
        buttons[0:3],
        buttons[3:6],
        buttons[6:9]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_ttt_game(user_id):
    user_games[user_id] = {
        "board": empty_board(),
        "turn": "user"
    }

async def end_ttt_game(user_id):
    if user_id in user_games:
        del user_games[user_id]

# --------------------------
# Bot Command Handlers
# --------------------------

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

@bot.on_message(filters.command("ttt"))
async def ttt_start_handler(client, message):
    user_id = message.from_user.id
    await start_ttt_game(user_id)
    game = user_games[user_id]
    text = "Let's play Tic Tac Toe! You are X, I am O.\n\n" \
           "Make your move by pressing a number below:\n\n" \
           f"{render_board_text(game['board'])}"
    markup = build_board_markup(game['board'])
    await message.reply_text(text, reply_markup=markup)

# --------------------------
# Callback query handler for Tic Tac Toe
# --------------------------

@bot.on_callback_query(filters.regex(r"ttt_\d"))
async def ttt_callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    if user_id not in user_games:
        await callback_query.answer("You have no active Tic Tac Toe game. Send /ttt to start one.", show_alert=True)
        return

    game = user_games[user_id]
    board = game['board']

    # User move index
    try:
        move_index = int(data.split("_")[1])
    except:
        await callback_query.answer("Invalid move.")
        return

    if board[move_index] != " ":
        await callback_query.answer("That cell is already taken! Choose another.", show_alert=True)
        return

    # User move
    board[move_index] = "X"

    winner = check_winner(board)
    if winner:
        # Game over after user move
        if winner == "X":
            text = f"You won! 🎉\n\nFinal board:\n{render_board_text(board)}"
        elif winner == "O":
            text = f"I won! 🤖\n\nFinal board:\n{render_board_text(board)}"
        else:
            text = f"It's a draw! 🤝\n\nFinal board:\n{render_board_text(board)}"
        markup = None
        await callback_query.message.reply_text(text)
        await callback_query.answer()
        await end_ttt_game(user_id)
        return

    # Bot move
    bot_move_minimax(board)

    winner = check_winner(board)
    if winner:
        # Game over after bot move
        if winner == "X":
            text = f"You won! 🎉\n\nFinal board:\n{render_board_text(board)}"
        elif winner == "O":
            text = f"I won! 🤖\n\nFinal board:\n{render_board_text(board)}"
        else:
            text = f"It's a draw! 🤝\n\nFinal board:\n{render_board_text(board)}"
        markup = None
        await callback_query.message.reply_text(text)
        await callback_query.answer()
        await end_ttt_game(user_id)
        return

    # Continue game
    text = f"Your turn! You're X.\n\n{render_board_text(board)}"
    markup = build_board_markup(board)
    await callback_query.message.reply_text(text, reply_markup=markup)
    await callback_query.answer()

# --------------------------
# Daily scheduled messages
# --------------------------

async def send_good_morning():
    await bot.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

async def send_good_night():
    await bot.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

scheduler.add_job(send_good_morning, trigger='cron', hour=7, minute=30)
scheduler.add_job(send_good_night, trigger='cron', hour=22, minute=0)

# --------------------------
# Webhook endpoint for Telegram updates
# --------------------------

@app.post(f"/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    update = await request.json()
    await bot.process_update(update)
    return PlainTextResponse("ok")

@app.get("/")
async def root():
    return {"message": "Bestie Bot is running!"}

# --------------------------
# Startup and Shutdown Events
# --------------------------

@app.on_event("startup")
async def startup_event():
    await bot.start()
    scheduler.start()
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    set_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    async with httpx.AsyncClient() as client:
        response = await client.post(set_webhook_url, data={"url": webhook_url})
        print("Webhook set response:", response.json())

@app.on_event("shutdown")
async def shutdown_event():
    await bot.stop()
    scheduler.shutdown()

# --------------------------
# Run via uvicorn if executed directly
# --------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
