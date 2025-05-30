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
online_games = {}
chat_waiting = set()

def render_board_text(board):
    s = {"X": "❌", "O": "⚫", " ": "⬜"}
    rows = [" | ".join(s[board[i*3+j]] for j in range(3)) for i in range(3)]
    return "\n---------\n".join(rows)

def check_winner(board, p):
    return any(all(board[i] == p for i in line) for line in [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]])

def is_full(board): return all(s != " " for s in board)
def available_moves(board): return [i for i, s in enumerate(board) if s == " "]

def minimax(board, depth, is_max):
    if check_winner(board, "O"): return 10 - depth
    if check_winner(board, "X"): return depth - 10
    if is_full(board): return 0
    scores = []
    for move in available_moves(board):
        board[move] = "O" if is_max else "X"
        score = minimax(board, depth + 1, not is_max)
        board[move] = " "
        scores.append(score)
    return max(scores) if is_max else min(scores)

def bot_move(board):
    best = -1e9
    move = None
    for m in available_moves(board):
        board[m] = "O"
        score = minimax(board, 0, False)
        board[m] = " "
        if score > best:
            best = score
            move = m
    return move

def build_keyboard(board, prefix, with_chat=False):
    kb = []
    for i in range(3):
        row = []
        for j in range(3):
            idx = i * 3 + j
            if board[idx] == " ":
                row.append(InlineKeyboardButton(str(idx+1), callback_data=f"{prefix}_{idx}"))
            else:
                row.append(InlineKeyboardButton("❌" if board[idx] == "X" else "⚫", callback_data="noop"))
        kb.append(row)
    if with_chat:
        kb.append([InlineKeyboardButton("💬 Chat", callback_data=f"chat_{prefix}")])
    return InlineKeyboardMarkup(kb)

# --- Daily Scheduler ---
async def send_daily_message():
    try:
        if quotes:
            await bot.send_message(BESTIE_USER_ID, random.choice(quotes))
        if photo_files:
            await bot.send_photo(BESTIE_USER_ID, random.choice(photo_files))
        if song_files:
            await bot.send_audio(BESTIE_USER_ID, random.choice(song_files))
    except Exception:
        pass

async def daily_good_morning():
    await bot.send_message(BESTIE_USER_ID, "🌞 Good Morning Dumb! Hope you have a fantastic day! 😊")

async def daily_good_afternoon():
    await bot.send_message(BESTIE_USER_ID, "🌞 Good Afternoon Jigs! Read well and don't forget to text me huh! 😊")

async def daily_good_night():
    await bot.send_message(BESTIE_USER_ID, "🌙 Good Night Dumb! Have sweet dreams like gulab jamun but you are the sweetest! 😊")

def schedule_all():
    scheduler.add_job(send_daily_message, "cron", hour=9, minute=0)
    scheduler.add_job(lambda: asyncio.create_task(daily_good_morning()), "cron", hour=7, minute=0)
    scheduler.add_job(lambda: asyncio.create_task(daily_good_afternoon()), "cron", hour=13, minute=30)
    scheduler.add_job(lambda: asyncio.create_task(daily_good_night()), "cron", hour=22, minute=30)

# --- Bot Handlers ---
@bot.on_message(filters.command("start"))
async def start_handler(client, msg):
    await msg.reply_text("Hey bestie! Type /ttt to play Tic Tac Toe with me, or /onlinettt to find a human opponent!")

@bot.on_message(filters.command("ttt"))
async def ttt(client, msg):
    uid = msg.from_user.id
    board = [" "] * 9
    games[uid] = board
    await msg.reply_text("You're ❌ (X). Let's start!\n" + render_board_text(board), reply_markup=build_keyboard(board, "ttt"))

@bot.on_callback_query(filters.regex(r"ttt_(\d)"))
async def single_move(client, cq):
    uid = cq.from_user.id
    board = games.get(uid)
    if not board: return await cq.answer("No game in progress", show_alert=True)
    move = int(cq.data.split("_")[1])
    if board[move] != " ": return await cq.answer("Invalid move", show_alert=True)
    board[move] = "X"
    if check_winner(board, "X"):
        del games[uid]
        return await cq.message.edit_text(render_board_text(board) + "\nYou win! 🎉")
    if is_full(board):
        del games[uid]
        return await cq.message.edit_text(render_board_text(board) + "\nIt's a draw!")
    board[bot_move(board)] = "O"
    if check_winner(board, "O"):
        del games[uid]
        return await cq.message.edit_text(render_board_text(board) + "\nI win! 😎")
    await cq.message.edit_text("Your move!\n" + render_board_text(board), reply_markup=build_keyboard(board, "ttt"))
    await cq.answer()

@bot.on_message(filters.command("onlinettt"))
async def online(client, msg):
    uid = msg.from_user.id
    if uid in waiting_queue:
        return await msg.reply("Already in queue!")
    if waiting_queue:
        x_id, o_id = waiting_queue.pop(0), uid
        board = [" "] * 9
        kb = build_keyboard(board, f"multi_{x_id}_{o_id}", with_chat=True)
        txt = render_board_text(board)
        m1 = await bot.send_message(x_id, f"🎮 You're ❌\n{txt}", reply_markup=kb)
        m2 = await bot.send_message(o_id, f"🎮 You're ⚫\n{txt}", reply_markup=kb)
        online_games[(x_id, o_id)] = {"board": board, "messages": {x_id: m1, o_id: m2}}
    else:
        waiting_queue.append(uid)
        await msg.reply("Waiting for opponent...")

@bot.on_callback_query(filters.regex(r"multi_(\d+)_(\d+)_(\d)"))
async def multiplayer_move(client, cq):
    x, o, idx = map(int, cq.data.split("_")[1:])
    uid = cq.from_user.id
    key = (x, o)
    game = online_games.get(key)
    if not game: return await cq.answer("Game not found", show_alert=True)
    board = game["board"]
    turn = "X" if board.count("X") <= board.count("O") else "O"
    if (turn == "X" and uid != x) or (turn == "O" and uid != o):
        return await cq.answer("Not your turn!", show_alert=True)
    if board[idx] != " ": return await cq.answer("Invalid move!", show_alert=True)
    board[idx] = turn
    txt = render_board_text(board)
    markup = build_keyboard(board, f"multi_{x}_{o}", with_chat=True)
    for uid_, msg_ in game["messages"].items():
        await msg_.edit_text(txt, reply_markup=markup)
    if check_winner(board, turn):
        del online_games[key]
        await bot.send_message(x, f"{turn} wins! 🔥")
        await bot.send_message(o, f"{turn} wins! 🔥")
    elif is_full(board):
        del online_games[key]
        await bot.send_message(x, "Draw!")
        await bot.send_message(o, "Draw!")
    await cq.answer()

@bot.on_callback_query(filters.regex(r"chat_multi_(\d+)_(\d+)"))
async def chat_request(client, cq):
    chat_waiting.add(cq.from_user.id)
    await cq.answer("Send your message now", show_alert=True)

@bot.on_message(filters.private & ~filters.command())
async def chat_msg(client, msg):
    if msg.from_user.id not in chat_waiting:
        return
    chat_waiting.remove(msg.from_user.id)
    opp = None
    for (x, o), game in online_games.items():
        if msg.from_user.id == x: opp = o
        elif msg.from_user.id == o: opp = x
    if opp:
        await bot.send_message(opp, f"💬 Message from your opponent:\n\n{msg.text or '<non-text>'}")
        await msg.reply("✅ Sent!")
    else:
        await msg.reply("You're not in a game!")

# --- FastAPI Webhook Handler ---
@app.post(f"/{BOT_TOKEN}")
async def webhook(req: Request):
    try:
        data = await req.body()
        update = Update.de_json(data.decode(), bot)
        await bot.process_update(update)
        return PlainTextResponse("ok")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return PlainTextResponse("error", status_code=500)

async def set_webhook():
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": f"{WEBHOOK_URL}/{BOT_TOKEN}"}
        )

# --- Entrypoint ---
if __name__ == "__main__":
    import uvicorn
    schedule_all()
    scheduler.start()
    asyncio.get_event_loop().run_until_complete(bot.start())
    asyncio.get_event_loop().run_until_complete(set_webhook())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
