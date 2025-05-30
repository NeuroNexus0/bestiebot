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

# Bestie user (change this to your user ID for daily messages)
BESTIE_USER_ID = 5672706639

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

# Single-player games (user_id -> board)
single_games = {}

# Online multiplayer games (chat_id -> game data)
# Game data: {
#   "players": [user_id1, user_id2],
#   "board": [...],
#   "turn": 0 or 1 (index of current player),
#   "message_id": int
# }
multi_games = {}

# Waiting queue for multiplayer matchmaking (list of user_ids)
waiting_queue = []

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

def build_board_keyboard(board, prefix="ttt_single"):
    kb = []
    for row in range(3):
        btn_row = []
        for col in range(3):
            idx = row * 3 + col
            if board[idx] == " ":
                btn_row.append(InlineKeyboardButton(str(idx+1), callback_data=f"{prefix}_{idx}"))
            else:
                symbol = {"X": "❌", "O": "⚫"}[board[idx]]
                btn_row.append(InlineKeyboardButton(symbol, callback_data="noop"))
        kb.append(btn_row)
    return InlineKeyboardMarkup(kb)

def build_multi_board_keyboard(board, game_id):
    kb = []
    for row in range(3):
        btn_row = []
        for col in range(3):
            idx = row * 3 + col
            if board[idx] == " ":
                btn_row.append(InlineKeyboardButton(str(idx+1), callback_data=f"ttt_multi_{game_id}_{idx}"))
            else:
                symbol = {"X": "❌", "O": "⚫"}[board[idx]]
                btn_row.append(InlineKeyboardButton(symbol, callback_data="noop"))
        kb.append(btn_row)
    return InlineKeyboardMarkup(kb)

# --- Single-player functions ---

async def start_single_game(user_id):
    board = [" "] * 9
    single_games[user_id] = board
    text = "Your turn! You're ❌ (X).\n\n" + render_board_text(board)
    markup = build_board_keyboard(board)
    return text, markup

async def handle_single_move(user_id, idx):
    board = single_games.get(user_id)
    if not board:
        return None, None, "No game in progress. Send /ttt to start."
    if board[idx] != " ":
        return None, None, "Invalid move!"

    board[idx] = "X"
    if check_winner(board, "X"):
        del single_games[user_id]
        return render_board_text(board) + "\n\nYou won! 🎉", None, None
    if is_board_full(board):
        del single_games[user_id]
        return render_board_text(board) + "\n\nIt's a draw!", None, None

    bot_idx = bot_move(board)
    if bot_idx is not None:
        board[bot_idx] = "O"

    if check_winner(board, "O"):
        del single_games[user_id]
        return render_board_text(board) + "\n\nI won! 😎", None, None
    if is_board_full(board):
        del single_games[user_id]
        return render_board_text(board) + "\n\nIt's a draw!", None, None

    return "Your turn! You're ❌ (X).\n\n" + render_board_text(board), build_board_keyboard(board), None

# --- Multiplayer matchmaking and game logic ---

import time
import uuid

MULTI_GAME_TIMEOUT = 600  # 10 minutes

# To track waiting players with timestamps
waiting_players = {}

async def start_multiplayer_game(user_id):
    # If user already in waiting, tell them to wait
    if user_id in waiting_players:
        return f"You're already in the multiplayer queue. Waiting for opponent...", None
    
    # If user already in a game, prevent starting another
    for g in multi_games.values():
        if user_id in g["players"]:
            return "You're already in a multiplayer game!", None

    # Add user to waiting queue with timestamp
    waiting_players[user_id] = time.time()

    # Check if there is another player waiting
    if len(waiting_players) < 2:
        return "Waiting for an opponent to join... (timeout after 10 minutes)", None

    # Find another waiting player (not self)
    for other_user, ts in waiting_players.items():
        if other_user != user_id:
            # Start game between user_id and other_user
            game_id = str(uuid.uuid4())
            board = [" "] * 9
            multi_games[game_id] = {
                "players": [user_id, other_user],
                "board": board,
                "turn": 0,
                "created_at": time.time(),
                "message_id": None,
                "chat_id": None
            }
            # Remove both from waiting
            del waiting_players[user_id]
            del waiting_players[other_user]
            text = f"Multiplayer Tic Tac Toe started!\n\nPlayer 1 (❌): {user_id}\nPlayer 2 (⚫): {other_user}\n\n" + render_board_text(board)
            markup = build_multi_board_keyboard(board, game_id)
            return text, markup

    return "Waiting for an opponent to join... (timeout after 10 minutes)", None

async def handle_multiplayer_move(user_id, game_id, idx):
    game = multi_games.get(game_id)
    if not game:
        return None, None, "This multiplayer game no longer exists."

    if user_id not in game["players"]:
        return None, None, "You're not a player in this game."

    if game["players"][game["turn"]] != user_id:
        return None, None, "It's not your turn!"

    board = game["board"]

    if board[idx] != " ":
        return None, None, "Invalid move!"

    # Mark move
    player_symbol = "X" if game["turn"] == 0 else "O"
    board[idx] = player_symbol

    # Check winner or draw
    if check_winner(board, player_symbol):
        del multi_games[game_id]
        text = render_board_text(board) + f"\n\nPlayer {game['turn'] + 1} ({player_symbol}) won! 🎉"
        return text, None, None

    if is_board_full(board):
        del multi_games[game_id]
        text = render_board_text(board) + "\n\nIt's a draw!"
        return text, None, None

    # Switch turn
    game["turn"] = 1 - game["turn"]

    text = f"Player 1 (❌): {game['players'][0]}\nPlayer 2 (⚫): {game['players'][1]}\n\n" + render_board_text(board)
    markup = build_multi_board_keyboard(board, game_id)
    return text, markup, None

# --- Telegram Handlers ---

@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nTry these commands:\n"
        "/quote – for a sweet message 💬\n"
        "/photo or /vibe – for a surprise picture 📸\n"
        "/music – for a random vibe 🎶\n"
        "/id – to get your user ID 🔍\n"
        "/ttt – play single-player Tic Tac Toe 🎮\n"
        "/ttt_online – play multiplayer Tic Tac Toe 🎮 (matchmake with others)"
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

# Single player Tic Tac Toe
@bot.on_message(filters.command("ttt"))
async def ttt(client, message):
    user_id = message.from_user.id
    text, markup = await start_single_game(user_id)
    await message.reply(text, reply_markup=markup)

@bot.on_callback_query(filters.regex(r"ttt_single_\d"))
async def single_ttt_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data  # format: ttt_single_<idx>
    idx = int(data.split("_")[-1])
    text, markup, error = await handle_single_move(user_id, idx)
    if error:
        await callback_query.answer(error, show_alert=True)
        return
    await callback_query.message.edit_text(text, reply_markup=markup)
    await callback_query.answer()

# Multiplayer Tic Tac Toe
@bot.on_message(filters.command("ttt_online"))
async def ttt_online(client, message):
    user_id = message.from_user.id
    text, markup = await start_multiplayer_game(user_id)
    await message.reply(text, reply_markup=markup)

@bot.on_callback_query(filters.regex(r"ttt_multi_[a-f0-9\-]+_\d"))
async def multi_ttt_callback(client, callback_query):
    data = callback_query.data  # format: ttt_multi_<game_id>_<idx>
    parts = data.split("_")
    game_id = parts[2]
    idx = int(parts[3])
    user_id = callback_query.from_user.id
    text, markup, error = await handle_multiplayer_move(user_id, game_id, idx)
    if error:
        await callback_query.answer(error, show_alert=True)
        return
    await callback_query.message.edit_text(text, reply_markup=markup)
    await callback_query.answer()

@bot.on_callback_query(filters.regex("noop"))
async def noop_callback(client, callback_query):
    # Do nothing for buttons that don't need action
    await callback_query.answer()

# --- Scheduled daily messages ---

async def send_good_morning():
    try:
        await bot.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")
    except Exception:
        pass

async def send_good_night():
    try:
        await bot.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")
    except Exception:
        pass

scheduler.add_job(send_good_morning, "cron", hour=7, minute=30)
scheduler.add_job(send_good_night, "cron", hour=22, minute=0)

scheduler.start()

# --- FastAPI webhook handlers ---

@app.get("/")
async def root():
    return PlainTextResponse("Bot is running!")

@app.post("/webhook")
async def webhook(request: Request):
    json_data = await request.json()
    update = Update.de_json(json_data)
    await bot.process_updates([update])
    return PlainTextResponse("ok")

# --- Startup and webhook set ---

@app.on_event("startup")
async def startup_event():
    # Set webhook for Render or similar environment
    async with httpx.AsyncClient() as client:
        url = f"{WEBHOOK_URL}/webhook"
        await bot.start()
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            data={"url": url}
        )

@app.on_event("shutdown")
async def shutdown_event():
    await bot.stop()

# --- Run Uvicorn ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT)
