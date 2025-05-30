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
online_games = {}  # key: (x_id, o_id), value: {"board": board, "messages": {x_id: msg1, o_id: msg2}}
rematch_requests = {}

# New: track users in chat mode for multiplayer games
chat_waiting_for_message = set()  # user_ids waiting to send a chat message

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
        # Add chat button in a new row
        kb.append([InlineKeyboardButton("💬 Chat", callback_data=f"chat_{prefix}")])
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
        txt = render_board_text(board)
        m1 = await bot.send_message(x_id, f"🔁 Rematch started! You're ❌\n\n{txt}", reply_markup=markup)
        m2 = await bot.send_message(o_id, f"🔁 Rematch started! You're ⚫\nWaiting for ❌\n\n{txt}", reply_markup=markup)
        online_games[(x_id, o_id)] = {"board": board, "messages": {x_id: m1, o_id: m2}}
        await cq.message.delete()
    else:
        await cq.answer("Waiting for opponent to accept rematch")

# --- In-Game Chat ---

@bot.on_callback_query(filters.regex(r"chat_multi_(\d+)_(\d+)"))
async def chat_button_handler(client, cq):
    user_id = cq.from_user.id
    data = cq.data.split("_")
    x_id, o_id = int(data[2]), int(data[3])
    # Only allow chatting if user is part of game
    if (x_id, o_id) not in online_games and (o_id, x_id) not in online_games:
        await cq.answer("Game no longer active.", show_alert=True)
        return
    chat_waiting_for_message.add(user_id)
    await cq.answer("Please send your message now.", show_alert=True)

@bot.on_message(filters.private & ~filters.command())
async def chat_message_forwarder(client, msg):
    user_id = msg.from_user.id
    if user_id not in chat_waiting_for_message:
        return  # Not in chat mode, ignore

    # Find opponent id from active game
    opponent_id = None
    for (x_id, o_id), game in online_games.items():
        if user_id == x_id:
            opponent_id = o_id
            break
        elif user_id == o_id:
            opponent_id = x_id
            break
    if not opponent_id:
        chat_waiting_for_message.discard(user_id)
        await msg.reply_text("You are not in a game currently.")
        return

    chat_waiting_for_message.discard(user_id)
    # Forward message to opponent with info who sent it
    await bot.send_message(opponent_id, f"💬 Message from your opponent:\n\n{msg.text or '<non-text message>'}")

    await msg.reply_text("✅ Your message was sent!")

# --- Other bot commands and handlers (quotes, pics, songs, etc.) can be added here as needed ---

# --- Webhook FastAPI Setup (optional) ---

@app.post("/")
async def webhook(request: Request):
    data = await request.body()
    update = Update.de_json(data.decode(), bot)
    await bot.process_updates([update])
    return PlainTextResponse("OK")

async def set_webhook():
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": WEBHOOK_URL})

if __name__ == "__main__":
    import uvicorn
    scheduler.start()
    asyncio.get_event_loop().run_until_complete(bot.start())
    asyncio.get_event_loop().run_until_complete(set_webhook())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
