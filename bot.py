import os
import random
import asyncio
import pytz
import httpx

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
BESTIE_USER_ID = 5672706639  # Replace with your user ID

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

# --- Single Player Tic Tac Toe Logic ---
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

# --- Multiplayer Tic Tac Toe Logic ---
waiting_queue = []
online_games = {}

@bot.on_message(filters.command("onlinettt"))
async def online_ttt_handler(client, msg):
    user_id = msg.from_user.id
    # Remove from queue if already in it (to avoid duplicates)
    for entry in waiting_queue:
        if entry["user_id"] == user_id:
            await msg.reply_text("You are already in the queue. Waiting for opponent...")
            return

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
    parts = cq.data.split("_")
    x_id, o_id, move = int(parts[1]), int(parts[2]), int(parts[3])
    board = online_games.get((x_id, o_id))
    uid = cq.from_user.id

    if not board:
        await cq.answer("Game not found", show_alert=True)
        return

    # Determine turn based on counts of X and O on board
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
        await bot.send_message(x_id, f"{text}\n\n{turn} wins! 🎉")
        await bot.send_message(o_id, f"{text}\n\n{turn} wins! 🎉")
    elif is_board_full(board):
        del online_games[(x_id, o_id)]
        await bot.send_message(x_id, f"{text}\n\nDraw! 🤝")
        await bot.send_message(o_id, f"{text}\n\nDraw! 🤝")
    else:
        await bot.send_message(x_id, text, reply_markup=markup)
        await bot.send_message(o_id, text, reply_markup=markup)

    await cq.answer()

# --- Misc Handlers ---
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
        "/quote – sweet message 💬\n/photo or /vibe – surprise pic 📸\n/music – vibe 🎶\n"
        "/id – your ID 🔍\n/ttt – play solo TTT 🎮\n/onlinettt – play with others 🌐\n"
        "/snl – play Snake and Ladder 🎲🐍🪜"
    )

@bot.on_message(filters.command("quote"))
async def quote_handler(client, msg):
    await msg.reply_text(random.choice(quotes))

@bot.on_message(filters.command(["photo", "vibe"]))
async def photo_handler(client, msg):
    if photo_files:
        await msg.reply_photo(random.choice(photo_files))
    else:
        await msg.reply_text("No photos available!")

@bot.on_message(filters.command("music"))
async def music_handler(client, msg):
    if song_files:
        await msg.reply_audio(audio=random.choice(song_files), caption="Vibe 🎧")
    else:
        await msg.reply_text("No songs available!")

@bot.on_message(filters.command("id"))
async def id_handler(client, msg):
    await msg.reply_text(f"Your user ID is: {msg.from_user.id}")

# --- Daily Messages ---
async def send_good_morning():
    await bot.send_message(BESTIE_USER_ID, "🌞 Good morning bestie! Hope your day is as lovely as you are 💖")

async def send_good_night():
    await bot.send_message(BESTIE_USER_ID, "🌙 Good night bestie! Sweet dreams and peaceful rest 💫")

scheduler.add_job(send_good_morning, 'cron', hour=7, minute=30)
scheduler.add_job(send_good_night, 'cron', hour=22, minute=0)

# --- Snake and Ladder Game ---
snake_ladder_games = {}

snakes = {
    16: 6,
    48: 26,
    49: 11,
    56: 53,
    62: 19,
    64: 60,
    87: 24,
    93: 73,
    95: 75,
    98: 78,
}

ladders = {
    1: 38,
    4: 14,
    9: 31,
    21: 42,
    28: 84,
    36: 44,
    51: 67,
    71: 91,
    80: 100,
}

def build_snake_ladder_keyboard():
    kb = [
        [InlineKeyboardButton("🎲 Roll Dice", callback_data="roll_dice")],
        [InlineKeyboardButton("🚪 Quit Game", callback_data="quit_snl")]
    ]
    return InlineKeyboardMarkup(kb)

def render_snake_ladder_board(pos):
    bar_length = 20
    filled_length = int(pos / 100 * bar_length)
    bar = "🟩" * filled_length + "⬜" * (bar_length - filled_length)
    return f"🏁 Position: {pos}/100\n{bar}"

@bot.on_message(filters.command("snl"))
async def start_snl_game(client, message):
    user_id = message.from_user.id
    snake_ladder_games[user_id] = 0
    await message.reply_text(
        "🐍🪜 Snake and Ladder game started! Reach 100 to win.\nRoll the dice!",
        reply_markup=build_snake_ladder_keyboard()
    )

@bot.on_callback_query(filters.regex("roll_dice"))
async def roll_dice_handler(client, cq):
    user_id = cq.from_user.id
    if user_id not in snake_ladder_games:
        await cq.answer("You don't have an active game. Use /snl to start.", show_alert=True)
        return

    pos = snake_ladder_games[user_id]
    dice = random.randint(1, 6)
    new_pos = pos + dice
    if new_pos > 100:
        new_pos = pos  # can't move if overshoot
    else:
        # Check snakes or ladders
        if new_pos in snakes:
            new_pos = snakes[new_pos]
        elif new_pos in ladders:
            new_pos = ladders[new_pos]

    snake_ladder_games[user_id] = new_pos
    board_text = render_snake_ladder_board(new_pos)
    if new_pos == 100:
        await cq.message.edit_text(f"{board_text}\n🎉 You won the Snake and Ladder game! Congratulations!")
        del snake_ladder_games[user_id]
    else:
        await cq.message.edit_text(f"You rolled a {dice}!\n{board_text}",
                                   reply_markup=build_snake_ladder_keyboard())
    await cq.answer()

@bot.on_callback_query(filters.regex("quit_snl"))
async def quit_snl_handler(client, cq):
    user_id = cq.from_user.id
    if user_id in snake_ladder_games:
        del snake_ladder_games[user_id]
    await cq.message.edit_text("Game ended. Use /snl anytime to start a new Snake and Ladder game!")
    await cq.answer()

# --- FastAPI webhook endpoint ---
@app.post("/")
async def receive_update(request: Request):
    data = await request.json()
    await bot.process_new_updates([data])
    return PlainTextResponse("ok")

# --- Startup/shutdown ---
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    # Set webhook with retry logic
    async with httpx.AsyncClient() as client:
        for _ in range(5):
            try:
                resp = await client.post(f"{WEBHOOK_URL}/setWebhook", json={"url": WEBHOOK_URL})
                if resp.status_code == 200:
                    break
            except Exception:
                await asyncio.sleep(2)

@app.on_event("shutdown")
async def shutdown_event():
    await bot.stop()

# --- Run bot and FastAPI together ---
if __name__ == "__main__":
    import uvicorn
    bot.start()
    uvicorn.run(app, host="0.0.0.0", port=PORT)
