import os
import random
import asyncio
import time
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

# --- Tic Tac Toe single player logic ---

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

def build_board_keyboard(board, online=False, user_id=None):
    kb = []
    for row in range(3):
        btn_row = []
        for col in range(3):
            idx = row * 3 + col
            if board[idx] == " ":
                cb_data = f"ttt_online_{idx}" if online else f"ttt_{idx}"
                btn_row.append(InlineKeyboardButton(str(idx+1), callback_data=cb_data))
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

# --- Online Multiplayer Tic Tac Toe ---

waiting_players = set()  # user_ids waiting for match
online_games = {}  # (user1_id, user2_id) -> {board, turn, last_move_time}
user_to_opponent = {}  # user_id -> opponent_id

ONLINE_TIMEOUT = 10 * 60  # 10 minutes timeout for inactivity (seconds)

def get_symbols_for_online_game(user_id, opponent_id):
    # Assign symbols based on sorted user_id order (lowest is X, highest is O)
    if user_id < opponent_id:
        return "X", "O"
    else:
        return "O", "X"

def opponent_id_for(user_id):
    return user_to_opponent.get(user_id)

def game_key_for_users(u1, u2):
    return tuple(sorted([u1, u2]))

async def ttt_online_start(client, message):
    user_id = message.from_user.id
    if user_id in waiting_players or user_id in user_to_opponent:
        await message.reply_text("You are already waiting for or in an online game!")
        return

    # Clean old games and waiting players timeout
    now = time.time()
    to_remove = []
    for w in waiting_players:
        # If user waited for too long, remove them
        # (Optional: implement last wait time if needed)
        pass
    for game_k, gdata in list(online_games.items()):
        if now - gdata["last_move_time"] > ONLINE_TIMEOUT:
            # timeout: notify both players and remove game
            u1, u2 = game_k
            try:
                await client.send_message(u1, "Your online Tic Tac Toe game timed out due to inactivity.")
            except:
                pass
            try:
                await client.send_message(u2, "Your online Tic Tac Toe game timed out due to inactivity.")
            except:
                pass
            online_games.pop(game_k)
            user_to_opponent.pop(u1, None)
            user_to_opponent.pop(u2, None)

    if waiting_players:
        opponent_id = waiting_players.pop()
        board = [" "] * 9
        game_k = game_key_for_users(user_id, opponent_id)
        online_games[game_k] = {
            "board": board,
            "turn": user_id,  # last joined user starts first
            "last_move_time": time.time(),
        }
        user_to_opponent[user_id] = opponent_id
        user_to_opponent[opponent_id] = user_id

        sym_user, sym_opp = get_symbols_for_online_game(user_id, opponent_id)

        start_text_user = (
            f"Tic Tac Toe online match started! You are {sym_user}.\nYour turn!\n\n"
            + render_board_text(board)
        )
        kb = build_board_keyboard(board, online=True)
        await client.send_message(user_id, start_text_user, reply_markup=kb)

        start_text_opp = (
            f"Tic Tac Toe online match started! You are {sym_opp}.\nWaiting for opponent's move...\n\n"
            + render_board_text(board)
        )
        await client.send_message(opponent_id, start_text_opp, reply_markup=kb)
    else:
        waiting_players.add(user_id)
        await message.reply_text("Waiting for an opponent... I'll let you know when someone joins!")

async def handle_online_move(user_id, idx):
    opponent = opponent_id_for(user_id)
    if not opponent:
        return None, None, "You are not in an online game."

    game_k = game_key_for_users(user_id, opponent)
    game = online_games.get(game_k)
    if not game:
        user_to_opponent.pop(user_id, None)
        user_to_opponent.pop(opponent, None)
        return None, None, "Game data missing or expired."

    board = game["board"]
    turn = game["turn"]
    if turn != user_id:
        return None, None, "It's not your turn."

    # Get user symbols
    sym_user, sym_opp = get_symbols_for_online_game(user_id, opponent)

    if board[idx] != " ":
        return None, None, "Invalid move!"

    # Place user's symbol
    board[idx] = sym_user

    # Update last move time
    game["last_move_time"] = time.time()

    # Check if user won
    if check_winner(board, sym_user):
        # Send final board and message to both
        final_board = render_board_text(board)
        await bot.send_message(user_id, final_board + "\n\nYou won! 🎉")
        await bot.send_message(opponent, final_board + "\n\nYou lost! 😢")
        # Clean up
        online_games.pop(game_k)
        user_to_opponent.pop(user_id, None)
        user_to_opponent.pop(opponent, None)
        return None, None, None

    if is_board_full(board):
        final_board = render_board_text(board)
        await bot.send_message(user_id, final_board + "\n\nIt's a draw!")
        await bot.send_message(opponent, final_board + "\n\nIt's a draw!")
        online_games.pop(game_k)
        user_to_opponent.pop(user_id, None)
        user_to_opponent.pop(opponent, None)
        return None, None, None

    # Switch turn to opponent
    game["turn"] = opponent

    # Send updated boards
    board_text_user = "Waiting for opponent's move...\n\n" + render_board_text(board)
    board_text_opp = "Your turn!\n\n" + render_board_text(board)

    kb_user = build_board_keyboard(board, online=True)
    kb_opp = build_board_keyboard(board, online=True)

    # Update messages
    try:
        await bot.send_message(user_id, board_text_user, reply_markup=kb_user)
        await bot.send_message(opponent, board_text_opp, reply_markup=kb_opp)
    except:
        pass

    return None, None, None

# --- Telegram Handlers ---

@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nTry these commands:\n"
        "/quote – for a sweet message 💬\n"
        "/photo or /vibe – for a surprise picture 📸\n"
        "/music – for a random vibe 🎶\n"
        "/id – to get your user ID 🔍\n"
        "/ttt – play Tic Tac Toe vs bot 🎮\n"
        "/ttt_online – play Tic Tac Toe online with others 🕹️"
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

@bot.on_message(filters.command("ttt_online"))
async def ttt_online(client, message):
    await ttt_online_start(client, message)

@bot.on_callback_query(filters.regex(r"ttt_(\d+)"))
async def single_or_online_move(client, callback):
    data = callback.data
    user_id = callback.from_user.id

    if data.startswith("ttt_online_"):
        idx = int(data.split("_")[-1])
        text, markup, error = await handle_online_move(user_id, idx)
        if error:
            await callback.answer(error, show_alert=True)
        else:
            # We do not edit inline messages here; messages are sent fresh each time
            await callback.answer()
    else:
        # Single player move
        idx = int(data.split("_")[-1])
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

async def send_good_morning
