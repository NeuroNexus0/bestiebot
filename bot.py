# --- Imports ---
import os
import random
import asyncio
import pytz
import httpx

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Environment Setup ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

# --- Initialize bot, web app and scheduler ---
bot = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app = FastAPI()
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))

# --- User ID for daily bestie messages ---
BESTIE_USER_ID = 5672706639

# --- Content pools ---
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

# --- Single Player Game Logic ---
games = {}

def render_board_text(board):
    symbol_map = {"X": "❌", "O": "⚫", " ": "⬜"}
    rows = [" | ".join(symbol_map[board[j + i * 3]] for j in range(3)) for i in range(3)]
    return "\n---------\n".join(rows)

def check_winner(board, player):
    wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    return any(all(board[i] == player for i in line) for line in wins)

def is_board_full(board):
    return all(space != " " for space in board)

def get_available_moves(board):
    return [i for i, v in enumerate(board) if v == " "]

# Minimax algorithm for unbeatable bot
def minimax(board, depth, is_max):
    if check_winner(board, "O"): return 10 - depth
    if check_winner(board, "X"): return depth - 10
    if is_board_full(board): return 0

    scores = []
    for move in get_available_moves(board):
        board[move] = "O" if is_max else "X"
        score = minimax(board, depth + 1, not is_max)
        board[move] = " "
        scores.append(score)
    return max(scores) if is_max else min(scores)

def bot_move(board):
    best = -float('inf')
    move = None
    for m in get_available_moves(board):
        board[m] = "O"
        score = minimax(board, 0, False)
        board[m] = " "
        if score > best:
            best = score
            move = m
    return move

def build_board_keyboard(board, prefix="ttt"):
    kb = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            if board[i] == " ":
                row.append(InlineKeyboardButton(str(i + 1), callback_data=f"{prefix}_{i}"))
            else:
                row.append(InlineKeyboardButton({"X": "❌", "O": "⚫"}[board[i]], callback_data="noop"))
        kb.append(row)
    return InlineKeyboardMarkup(kb)

async def start_game(uid):
    board = [" "] * 9
    games[uid] = board
    return "Your turn! You're ❌ (X).\n\n" + render_board_text(board), build_board_keyboard(board)

async def handle_move(uid, idx):
    board = games.get(uid)
    if not board or board[idx] != " ":
        return None, None, "Invalid or no game."
    
    board[idx] = "X"
    if check_winner(board, "X"):
        del games[uid]
        return render_board_text(board) + "\n\nYou won! 🎉", None, None

    if is_board_full(board):
        del games[uid]
        return render_board_text(board) + "\n\nDraw!", None, None

    bot_idx = bot_move(board)
    if bot_idx is not None:
        board[bot_idx] = "O"
        if check_winner(board, "O"):
            del games[uid]
            return render_board_text(board) + "\n\nI won! 😎", None, None
        if is_board_full(board):
            del games[uid]
            return render_board_text(board) + "\n\nDraw!", None, None

    return "Your turn! You're ❌ (X).\n\n" + render_board_text(board), build_board_keyboard(board), None

# --- Multiplayer Logic ---
waiting_queue = []
online_games = {}

@bot.on_message(filters.command("onlinettt"))
async def online_ttt_handler(client, msg):
    user_id = msg.from_user.id
    if waiting_queue and waiting_queue[0]["user_id"] != user_id:
        opponent = waiting_queue.pop(0)
        x_id, o_id = opponent["user_id"], user_id
        board = [" "] * 9
        online_games[(x_id, o_id)] = board
        markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}")
        board_text = render_board_text(board)
        await bot.send_message(x_id, f"🎮 Multiplayer game started! You're ❌\n\n{board_text}", reply_markup=markup)
        await bot.send_message(o_id, f"🎮 Multiplayer game started! You're ⚫\nWaiting for ❌\n\n{board_text}", reply_markup=markup)
    else:
        waiting_queue.append({"user_id": user_id})
        await msg.reply_text("⏳ You're added to the queue. Waiting for another player...")

@bot.on_callback_query(filters.regex(r"multi_(\d+)_(\d+)_(\d)"))
async def multiplayer_move_handler(client, cq):
    x_id, o_id, move = map(int, cq.data.split("_")[1:])
    board = online_games.get((x_id, o_id))
    uid = cq.from_user.id

    if not board:
        await cq.answer("Game not found", show_alert=True)
        return

    turn = "X" if board.count("X") <= board.count("O") else "O"
    if (turn == "X" and uid != x_id) or (turn == "O" and uid != o_id):
        await cq.answer("Not your turn", show_alert=True)
        return

    if board[move] != " ":
        await cq.answer("Invalid move", show_alert=True)
        return

    board[move] = turn
    text = render_board_text(board)
    markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}")

    if check_winner(board, turn):
        del online_games[(x_id, o_id)]
        await bot.send_message(x_id, f"{text}\n\n{turn} wins!")
        await bot.send_message(o_id, f"{text}\n\n{turn} wins!")
    elif is_board_full(board):
        del online_games[(x_id, o_id)]
        await bot.send_message(x_id, f"{text}\n\nDraw!")
        await bot.send_message(o_id, f"{text}\n\nDraw!")
    else:
        await bot.send_message(x_id, text, reply_markup=markup)
        await bot.send_message(o_id, text, reply_markup=markup)

    await cq.answer()

# --- Misc Commands ---
@bot.on_callback_query(filters.regex("noop"))
async def noop_handler(client, cq):
    await cq.answer()

@bot.on_message(filters.command("ttt"))
async def ttt_handler(client, msg):
    uid = msg.from_user.id
    text, kb = await start_game(uid)
    await msg.reply_text(text, reply_markup=kb)

@bot.on_callback_query(filters.regex(r"ttt_\d"))
async def ttt_cb(client, cq):
    uid = cq.from_user.id
    idx = int(cq.data.split("_")[1])
    text, kb, err = await handle_move(uid, idx)
    if err:
        await cq.answer(err, show_alert=True)
    else:
        await cq.message.edit_text(text, reply_markup=kb)
        await cq.answer()

@bot.on_message(filters.command("start"))
async def start_handler(client, msg):
    await msg.reply_text(
        "Hey Bestie! 💌\n\nI'm your special bot made with love.\nCommands:\n"
        "/quote – sweet message\n"
        "/photo – cute picture\n"
        "/song – song for your mood\n"
        "/ttt – play Tic Tac Toe singleplayer\n"
        "/onlinettt – find a friend to play multiplayer Tic Tac Toe\n"
        "/snl – play Snake and Ladder\n\n"
        "Use buttons to interact!"
    )

# --- Quote Command ---
@bot.on_message(filters.command("quote"))
async def quote_handler(client, msg):
    quote = random.choice(quotes)
    await msg.reply_text(quote)

# --- Photo Command ---
@bot.on_message(filters.command("photo"))
async def photo_handler(client, msg):
    photo_path = random.choice(photo_files)
    await msg.reply_photo(photo=photo_path)

# --- Song Command ---
@bot.on_message(filters.command("song"))
async def song_handler(client, msg):
    song_path = random.choice(song_files)
    await msg.reply_audio(audio=song_path)

# --- Snake and Ladder Game Setup ---

# Board mapping: squares 1 to 100
# Ladders and snakes mapped as start->end
SNL_LADDERS = {
    4: 14, 9: 31, 20: 38, 28: 84,
    40: 59, 51: 67, 63: 81, 71: 91
}
SNL_SNAKES = {
    17: 7, 54: 34, 62: 19, 64: 60,
    87: 24, 93: 73, 95: 75, 99: 78
}

snl_games = {}

def get_snl_position(pos):
    if pos in SNL_LADDERS:
        return SNL_LADDERS[pos], "Ladder! 🪜"
    elif pos in SNL_SNAKES:
        return SNL_SNAKES[pos], "Snake! 🐍"
    else:
        return pos, None

def snl_status_text(pos):
    return f"You're on square {pos}."

def build_snl_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Roll 🎲", callback_data="snl_roll")]]
    )

@bot.on_message(filters.command("snl"))
async def snl_start(client, msg):
    uid = msg.from_user.id
    snl_games[uid] = 1
    await msg.reply_text(
        "Welcome to Snake and Ladder!\n\n" + snl_status_text(1),
        reply_markup=build_snl_keyboard()
    )

@bot.on_callback_query(filters.regex("snl_roll"))
async def snl_roll_handler(client, cq):
    uid = cq.from_user.id
    pos = snl_games.get(uid, 1)
    roll = random.randint(1, 6)
    new_pos = pos + roll
    if new_pos > 100:
        new_pos = pos  # can't move if goes beyond 100
    msg = f"You rolled a {roll}.\n"
    final_pos, special = get_snl_position(new_pos)
    if special:
        msg += f"{special}\n"
    snl_games[uid] = final_pos
    msg += snl_status_text(final_pos)

    if final_pos == 100:
        msg += "\n🎉 Congratulations! You reached 100 and won the game! 🎉"
        del snl_games[uid]
        await cq.message.edit_text(msg, reply_markup=None)
    else:
        await cq.message.edit_text(msg, reply_markup=build_snl_keyboard())
    await cq.answer()

# --- Webhook setup for FastAPI ---
@app.post(f"/{BOT_TOKEN}")
async def bot_webhook(request: Request):
    update = Update.de_json(await request.json())
    await bot.process_update(update)
    return PlainTextResponse("ok")

# --- Start the scheduler to send daily messages ---
async def daily_bestie_message():
    quote = random.choice(quotes)
    photo_path = random.choice(photo_files)
    song_path = random.choice(song_files)
    try:
        await bot.send_photo(BESTIE_USER_ID, photo=photo_path, caption=quote)
        await bot.send_audio(BESTIE_USER_ID, audio=song_path)
    except Exception as e:
        print("Error sending daily message:", e)

scheduler.add_job(daily_bestie_message, "cron", hour=9, minute=0)

# --- Run bot and scheduler ---
if __name__ == "__main__":
    import uvicorn
    scheduler.start()
    bot.start()
    uvicorn.run(app, host="0.0.0.0", port=PORT)
    bot.stop()
