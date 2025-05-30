# --- Imports ---

import os
import random
import asyncio
import pytz
import httpx

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Update, Message
from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Environment Setup ---

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

bot = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app = FastAPI()
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))

BESTIE_USER_ID = 5672706639

# --- Content Pools ---

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

# --- Game Logic ---

games = {}
waiting_queue = []
online_games = {}  # (x_id, o_id): {board, messages}
rematch_requests = {}

def render_board_text(board):
    symbol_map = {"X": "❌", "O": "⚫", " ": "⬜"}
    rows = [" | ".join(symbol_map[board[j + i * 3]] for j in range(3)) for i in range(3)]
    return "\n---------\n".join(rows)

def check_winner(board, player):
    wins = [
        [0,1,2],[3,4,5],[6,7,8],
        [0,3,6],[1,4,7],[2,5,8],
        [0,4,8],[2,4,6]
    ]
    return any(all(board[i] == player for i in line) for line in wins)

def is_board_full(board):
    return all(space != " " for space in board)

def get_available_moves(board):
    return [i for i, v in enumerate(board) if v == " "]

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
    best, move = -float('inf'), None
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

# --- Single Player ---

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

# --- Multiplayer ---

@bot.on_message(filters.command("onlinettt"))
async def online_ttt_handler(client, msg):
    user_id = msg.from_user.id
    if waiting_queue and waiting_queue[0] != user_id:
        x_id, o_id = waiting_queue.pop(0), user_id
        board = [" "] * 9
        markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}")
        board_text = render_board_text(board)
        m1 = await bot.send_message(x_id, f"🎮 Multiplayer started! You're ❌\n\n{board_text}", reply_markup=markup)
        m2 = await bot.send_message(o_id, f"🎮 Multiplayer started! You're ⚫\nWaiting for ❌\n\n{board_text}", reply_markup=markup)
        online_games[(x_id, o_id)] = {"board": board, "messages": {x_id: m1, o_id: m2}}
    else:
        waiting_queue.append(user_id)
        await msg.reply_text("⏳ You're in the queue. Waiting for an opponent...")

@bot.on_callback_query(filters.regex(r"multi_(\d+)_(\d+)_(\d+)"))
async def multiplayer_move_handler(client, cq):
    x_id, o_id, move = map(int, cq.data.split("_")[1:])
    uid = cq.from_user.id
    game = online_games.get((x_id, o_id))
    if not game:
        await cq.answer("Game not found", show_alert=True)
        return
    board = game["board"]
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

    async def edit(msg_obj, txt): await msg_obj.edit_text(txt, reply_markup=markup)
    m1, m2 = game["messages"][x_id], game["messages"][o_id]

    if check_winner(board, turn):
        del online_games[(x_id, o_id)]
        rematch_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Rematch", callback_data=f"rematch_{x_id}_{o_id}")]
        ])
        await edit(m1, f"{text}\n\n{turn} wins!")
        await edit(m2, f"{text}\n\n{turn} wins!")
        await bot.send_message(x_id, "Ask for rematch 🔁", reply_markup=rematch_markup)
        await bot.send_message(o_id, "Ask for rematch 🔁", reply_markup=rematch_markup)
    elif is_board_full(board):
        del online_games[(x_id, o_id)]
        await edit(m1, f"{text}\n\nDraw!")
        await edit(m2, f"{text}\n\nDraw!")
    else:
        await edit(m1, text)
        await edit(m2, text)
    await cq.answer()

@bot.on_callback_query(filters.regex(r"rematch_(\d+)_(\d+)"))
async def rematch_request_handler(client, cq):
    x_id, o_id = map(int, cq.data.split("_")[1:])
    sender = cq.from_user.id
    key = tuple(sorted([x_id, o_id]))
    rematch_requests.setdefault(key, set()).add(sender)
    if len(rematch_requests[key]) == 2:
        del rematch_requests[key]
        board = [" "] * 9
        markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}")
        txt = render_board_text(board)
        m1 = await bot.send_message(x_id, f"🔁 Rematch started! You're ❌\n\n{txt}", reply_markup=markup)
        m2 = await bot.send_message(o_id, f"🔁 Rematch started! You're ⚫\n\n{txt}", reply_markup=markup)
        online_games[(x_id, o_id)] = {"board": board, "messages": {x_id: m1, o_id: m2}}
    else:
        await cq.answer("Rematch request sent. Waiting for opponent.", show_alert=True)

# --- In-Game Chat ---

@bot.on_message(filters.command("say") & filters.private)
async def say_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /say message")
        return
    uid = msg.from_user.id
    for (x_id, o_id), data in online_games.items():
        if uid in (x_id, o_id):
            peer = o_id if uid == x_id else x_id
            await bot.send_message(peer, f"💬 Message from your opponent:\n{parts[1]}")
            await msg.reply_text("Sent.")
            return
    await msg.reply_text("No active game found.")

# --- Misc ---

@bot.on_callback_query(filters.regex("noop"))
async def noop_handler(client, cq): await cq.answer()

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
        "Hey Dumb! 💌\n\nI'm your special bot made with love.\nCommands:\n"
        "/quote – sweet message 💬\n/photo or /vibe – surprise pic 📸\n/music – vibe 🎶\n"
        "/id – your ID 🔍\n/ttt – play solo TTT 🎮\n/onlinettt – play with others 🌐\n"
        "/say – send message to opponent 💬"
    )

@bot.on_message(filters.command("quote"))
async def quote_handler(client, msg): await msg.reply_text(random.choice(quotes))

@bot.on_message(filters.command(["photo", "vibe"]))
async def photo_handler(client, msg):
    if photo_files: await msg.reply_photo(random.choice(photo_files))
    else: await msg.reply_text("No photos!")

@bot.on_message(filters.command("music"))
async def music_handler(client, msg):
    if song_files: await msg.reply_audio(audio=random.choice(song_files), caption="Vibe 🎧")
    else: await msg.reply_text("No songs!")

@bot.on_message(filters.command("id"))
async def id_handler(client, msg): await msg.reply_text(f"Your user ID is: {msg.from_user.id}")

# --- Daily Messages ---

async def send_good_morning(): await bot.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! 💖")
async def send_good_afternoon(): await bot.send_message(BESTIE_USER_ID, "🌞 Good Afternoon Kritika! 💖🎶")
async def send_good_night(): await bot.send_message(BESTIE_USER_ID, "🌙 Good night Dumb Jigs 💫")

scheduler.add_job(send_good_morning, 'cron', hour=7, minute=30)
scheduler.add_job(send_good_afternoon, 'cron', hour=13, minute=30)
scheduler.add_job(send_good_night, 'cron', hour=22, minute=0)

# --- FastAPI Webhook ---

@app.post(f"/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    update_data = await request.json()
    update = Update.de_json(update_data, bot)
    await bot.process_update(update)
    return PlainTextResponse("ok")

@app.get("/")
async def root(): return {"message": "Bestie Bot is running!"}

@app.on_event("startup")
async def startup_event():
    await bot.start()
    scheduler.start()
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            data={"url": f"{WEBHOOK_URL}/{BOT_TOKEN}"}
        )

@app.on_event("shutdown")
async def shutdown_event():
    await bot.stop()
    scheduler.shutdown()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
