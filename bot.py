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
from datetime import datetime
from pytz import timezone

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
online_games = {}  # key: (x_id, o_id), value: {"board": board, "messages": {x_id: msg1, o_id: msg2}}
rematch_requests = {}

# Track users waiting to send chat message
chat_waiting_for_message = set()

# Track all users who started the bot for Good Morning message
users = set()

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

def build_board_keyboard(board, prefix="ttt", with_chat=False):
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
    if with_chat:
        kb.append([InlineKeyboardButton("💬 Chat", callback_data=f"chat_{prefix}")])
    return InlineKeyboardMarkup(kb)

# --- Single Player ---

@bot.on_message(filters.command("start"))
async def start_single_player(client, message):
    uid = message.from_user.id
    users.add(uid)  # Track user for Good Morning
    board = [" "] * 9
    games[uid] = board
    txt = "Your turn! You're ❌ (X).\n\n" + render_board_text(board)
    kb = build_board_keyboard(board)
    await message.reply_text(txt, reply_markup=kb)

@bot.on_callback_query(filters.regex(r"ttt_(\d+)"))
async def singleplayer_move(client, cq):
    uid = cq.from_user.id
    idx = int(cq.data.split("_")[1])
    board = games.get(uid)
    if not board or board[idx] != " ":
        await cq.answer("Invalid move or no game.", show_alert=True)
        return
    board[idx] = "X"
    if check_winner(board, "X"):
        del games[uid]
        await cq.message.edit_text(render_board_text(board) + "\n\nYou won! 🎉")
        return
    if is_board_full(board):
        del games[uid]
        await cq.message.edit_text(render_board_text(board) + "\n\nDraw!")
        return
    bot_idx = bot_move(board)
    if bot_idx is not None:
        board[bot_idx] = "O"
        if check_winner(board, "O"):
            del games[uid]
            await cq.message.edit_text(render_board_text(board) + "\n\nI won! 😎")
            return
        if is_board_full(board):
            del games[uid]
            await cq.message.edit_text(render_board_text(board) + "\n\nDraw!")
            return
    txt = "Your turn! You're ❌ (X).\n\n" + render_board_text(board)
    kb = build_board_keyboard(board)
    await cq.message.edit_text(txt, reply_markup=kb)
    await cq.answer()

# --- Multiplayer ---

@bot.on_message(filters.command("onlinettt"))
async def online_ttt_handler(client, msg):
    user_id = msg.from_user.id
    if user_id in waiting_queue:
        await msg.reply_text("⏳ You are already in the queue, waiting for an opponent...")
        return

    if waiting_queue and waiting_queue[0] != user_id:
        x_id, o_id = waiting_queue.pop(0), user_id
        board = [" "] * 9
        markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}", with_chat=True)
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
    # Determine turn
    turn = "X" if board.count("X") <= board.count("O") else "O"
    if (turn == "X" and uid != x_id) or (turn == "O" and uid != o_id):
        await cq.answer("Not your turn", show_alert=True)
        return
    if board[move] != " ":
        await cq.answer("Invalid move", show_alert=True)
        return
    board[move] = turn
    text = render_board_text(board)
    markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}", with_chat=True)

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
        markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}", with_chat=True)
        m1 = await bot.send_message(x_id, f"🔁 Rematch started! You're ❌\n\n{render_board_text(board)}", reply_markup=markup)
        m2 = await bot.send_message(o_id, f"🔁 Rematch started! You're ⚫\n\n{render_board_text(board)}", reply_markup=markup)
        online_games[(x_id, o_id)] = {"board": board, "messages": {x_id: m1, o_id: m2}}
        await cq.answer("Rematch started!")
    else:
        await cq.answer("Rematch requested. Waiting for opponent...")

# --- In-game chat ---

@bot.on_callback_query(filters.regex(r"chat_multi_(\d+)_(\d+)"))
async def chat_button_handler(client, cq):
    uid = cq.from_user.id
    # Register user to wait for message input
    chat_waiting_for_message.add(uid)
    await cq.answer("Please type your message now. It will be sent to your opponent.")

@bot.on_message()
async def chat_message_forwarder(client, message):
    uid = message.from_user.id
    if uid in chat_waiting_for_message:
        chat_waiting_for_message.remove(uid)
        # Find game where user is playing
        for (x_id, o_id), game in online_games.items():
            if uid == x_id:
                opponent = o_id
                break
            elif uid == o_id:
                opponent = x_id
                break
        else:
            await message.reply_text("You're not in a multiplayer game.")
            return
        try:
            await bot.send_message(opponent, f"💬 Message from your opponent:\n\n{message.text}")
            await message.reply_text("Message sent!")
        except Exception:
            await message.reply_text("Failed to send message to opponent.")
    # Else do nothing to other messages

# --- Daily Good Morning scheduler ---

async def daily_good_morning():
    for user_id in users:
        try:
            await bot.send_message(user_id, "🌞 Good Morning Dumb! Hope you have a fantastic day! 😊")
        except Exception:
            pass

def schedule_good_morning():
    ist = timezone("Asia/Kolkata")
    scheduler.add_job(
        lambda: asyncio.create_task(daily_good_morning()), 
        "cron", hour=7, minute=0, timezone=ist
    )

async def daily_good_afternoon():
    for user_id in users:
        try:
            await bot.send_message(user_id, "🌞 Good Afternoon Jigs! Read well and don't to forget to text me huh! 😊")
        except Exception:
            pass

def schedule_good_afternoon():
    ist = timezone("Asia/Kolkata")
    scheduler.add_job(
        lambda: asyncio.create_task(daily_good_morning()), 
        "cron", hour=13, minute=30, timezone=ist
    )

async def daily_good_night():
    for user_id in users:
        try:
            await bot.send_message(user_id, "🌞 Good Night Dumb! Have sweeet dreams like gulab jamun but u are the sweetest! 😊")
        except Exception:
            pass

def schedule_good_night():
    ist = timezone("Asia/Kolkata")
    scheduler.add_job(
        lambda: asyncio.create_task(daily_good_morning()), 
        "cron", hour=22, minute=30, timezone=ist
    )



# --- Webhook + FastAPI ---

@app.get("/")
async def root():
    return PlainTextResponse("BestieBot is running.")

@app.post(f"/{BOT_TOKEN}")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data)
    await bot.process_update(update)
    return PlainTextResponse("ok")

async def set_webhook():
    async with httpx.AsyncClient() as client:
        webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
        resp = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            data={"url": webhook_url}
        )
        if resp.status_code == 200:
            print("Webhook set successfully")
        else:
            print("Failed to set webhook:", resp.text)

if __name__ == "__main__":
    import uvicorn
    schedule_good_morning()
    scheduler.start()
    asyncio.get_event_loop().run_until_complete(set_webhook())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
