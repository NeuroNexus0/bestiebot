# --- Imports ---
import os
import random
import asyncio
import pytz
import httpx
import subprocess
import importlib
import sys
from io import StringIO
import datetime
from typing import Dict, Tuple, List, Optional, Union

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery,
    Update
)
from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job

# --- Environment Setup ---
API_ID = int(os.getenv("API_ID", 12345))
API_HASH = os.getenv("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-webhook-url.com")
PORT = int(os.getenv("PORT", 8000))

bot = Client("bestie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
app = FastAPI()
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))

# --- User Configuration ---
BESTIE_USER_ID = 5672706639  # Fill this with actual bestie user ID
MY_USER_ID = 7590978422      # Fill this with your actual user ID

# --- Content Pools ---
quotes = [
    "You're not just a star, you're my whole sky. ✨",
    "Your smile makes my day every time 😊",
    "You're the kindest soul I've ever met 💖",
    "Just a reminder: You're amazing. No doubt. 💫"
]

# --- Fill in the Blanks Questions Pool ---
daily_questions = [
    "Today I feel _______ because _______.",
    "My favorite memory with you is _______.",
    "If I could tell you one thing right now, it would be _______.",
    "The thing that made me smile today was _______.",
    "I'm grateful for _______ in my life.",
    "My biggest dream is _______.",
    "The song that describes my mood today is _______.",
    "If we could go anywhere together, I'd choose _______.",
    "The best part of my day was _______.",
    "Something I learned today is _______.",
    "My current favorite food is _______.",
    "If I had a superpower, it would be _______ so I could _______.",
    "The weather today makes me feel _______.",
    "I wish I could _______ with you right now.",
    "My spirit animal today would be _______ because _______."
]

# Split questions into morning and evening pools
random.shuffle(daily_questions)
split_index = len(daily_questions) // 2
questions_morning = daily_questions[:split_index]
questions_evening = daily_questions[split_index:]

# --- Question Settings ---
morning_question_time = "06:00"
evening_question_time = "18:00"
morning_question_count = 1
evening_question_count = 1

# --- Daily Question States ---
current_morning_question = {"question": "", "date": None, "answered": False}
current_evening_question = {"question": "", "date": None, "answered": False}

# --- Customizable Greetings ---
greetings = {
    "morning": "🌞 Good morning bestie have a nice day! 💖",
    "afternoon": "🌞 Good Afternoon Kritika Eat well! 💖🎶",
    "night": "🌙 Good night Dumb Jigs I Like u the most 💫"
}

# --- File Paths ---
CODE_FILE = "bot.py"
BACKUP_FILE = "bot_backup.py"
PHOTO_FOLDER = "photos"
SONG_FOLDER = "songs"

# --- Game State Storage ---
games: Dict[int, List[str]] = {}
waiting_queue: List[int] = []
online_games: Dict[Tuple[int, int], Dict] = {}
rematch_requests: Dict[Tuple[int, int], set] = {}

# --- Initialize Folders ---
try:
    os.makedirs(PHOTO_FOLDER, exist_ok=True)
    os.makedirs(SONG_FOLDER, exist_ok=True)
except Exception as e:
    print(f"Failed to create folders: {e}")
    sys.exit(1)

# --- Helper Functions ---
def render_board_text(board: List[str]) -> str:
    symbol_map = {"X": "❌", "O": "⚫", " ": "⬜"}
    rows = [" | ".join(symbol_map[board[j + i * 3]] for j in range(3)) for i in range(3)]
    return "\n---------\n".join(rows)

def check_winner(board: List[str], player: str) -> bool:
    wins = [
        [0,1,2],[3,4,5],[6,7,8],
        [0,3,6],[1,4,7],[2,5,8],
        [0,4,8],[2,4,6]
    ]
    return any(all(board[i] == player for i in line) for line in wins)

def is_board_full(board: List[str]) -> bool:
    return all(space != " " for space in board)

def get_available_moves(board: List[str]) -> List[int]:
    return [i for i, v in enumerate(board) if v == " "]

def minimax(board: List[str], depth: int, is_max: bool) -> int:
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

def bot_move(board: List[str]) -> Optional[int]:
    best, move = -float('inf'), None
    for m in get_available_moves(board):
        board[m] = "O"
        score = minimax(board, 0, False)
        board[m] = " "
        if score > best:
            best = score
            move = m
    return move

def build_board_keyboard(board: List[str], prefix: str = "ttt") -> InlineKeyboardMarkup:
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

def parse_time(time_str: str) -> Tuple[int, int]:
    """Parse HH:MM format time string into (hour, minute) tuple"""
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return hour, minute
    except ValueError:
        raise ValueError("Invalid time format. Use HH:MM (24-hour format)")

def reschedule_job(job_id: str, hour: int, minute: int) -> Job:
    """Reschedule an existing APScheduler job"""
    scheduler.remove_job(job_id)
    return scheduler.add_job(
        globals()[job_id],
        'cron',
        hour=hour,
        minute=minute,
        id=job_id
    )

# --- Daily Question Functions ---
def get_new_morning_question() -> str:
    """Get random questions from the morning pool"""
    if not questions_morning:
        return "How are you feeling today?"
    questions = random.sample(questions_morning, min(morning_question_count, len(questions_morning)))
    return "\n".join(questions) if morning_question_count > 1 else questions[0]

def get_new_evening_question() -> str:
    """Get random questions from the evening pool"""
    if not questions_evening:
        return "What was the highlight of your day?"
    questions = random.sample(questions_evening, min(evening_question_count, len(questions_evening)))
    return "\n".join(questions) if evening_question_count > 1 else questions[0]

async def send_morning_question():
    """Send morning question to bestie user at scheduled time"""
    today = datetime.date.today()
    
    # Check if we already sent a morning question today
    if current_morning_question["date"] == today:
        return
    
    # Get new question and update state
    new_questions = get_new_morning_question()
    if isinstance(new_questions, str):
        new_questions = [new_questions]
    
    current_morning_question["question"] = "\n".join(new_questions)
    current_morning_question["date"] = today
    current_morning_question["answered"] = False
    
    # Send questions to bestie
    question_text = (
        f"🌅 Morning Question Time! 🌅\n\n"
        f"📝 {current_morning_question['question']}\n\n"
        f"Reply with your answers! Your response will be shared with your special someone 💝"
    )
    
    await bot.send_message(BESTIE_USER_ID, question_text)

async def send_evening_question():
    """Send evening question to bestie user at scheduled time"""
    today = datetime.date.today()
    
    # Check if we already sent an evening question today
    if current_evening_question["date"] == today:
        return
    
    # Get new question and update state
    new_questions = get_new_evening_question()
    if isinstance(new_questions, str):
        new_questions = [new_questions]
    
    current_evening_question["question"] = "\n".join(new_questions)
    current_evening_question["date"] = today
    current_evening_question["answered"] = False
    
    # Send question to bestie
    question_text = (
        f"🌇 Evening Question Time! 🌇\n\n"
        f"📝 {current_evening_question['question']}\n\n"
        f"Reply with your answers! Your response will be shared with your special someone 💝"
    )
    
    await bot.send_message(BESTIE_USER_ID, question_text)

# --- Admin Question Management Handlers ---
@bot.on_message(filters.command("addmorningq") & filters.user(MY_USER_ID))
async def add_morning_question(client: Client, msg: Message):
    """Add a new question to the morning pool"""
    question = msg.text.split(maxsplit=1)
    if len(question) < 2:
        await msg.reply_text("Usage: /addmorningq <question>")
        return
    
    questions_morning.append(question[1])
    await msg.reply_text(f"✅ Added morning question:\n{question[1]}")

@bot.on_message(filters.command("addeveningq") & filters.user(MY_USER_ID))
async def add_evening_question(client: Client, msg: Message):
    """Add a new question to the evening pool"""
    question = msg.text.split(maxsplit=1)
    if len(question) < 2:
        await msg.reply_text("Usage: /addeveningq <question>")
        return
    
    questions_evening.append(question[1])
    await msg.reply_text(f"✅ Added evening question:\n{question[1]}")

@bot.on_message(filters.command("listquestions") & filters.user(MY_USER_ID))
async def list_questions(client: Client, msg: Message):
    """List all questions with indices"""
    morning_text = "🌅 Morning Questions:\n" + "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(questions_morning)
    ) if questions_morning else "No morning questions yet!"
    
    evening_text = "\n\n🌇 Evening Questions:\n" + "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(questions_evening)
    ) if questions_evening else "\nNo evening questions yet!"
    
    await msg.reply_text(morning_text + evening_text)

@bot.on_message(filters.command("removemq") & filters.user(MY_USER_ID))
async def remove_morning_question(client: Client, msg: Message):
    """Remove a morning question by index"""
    try:
        index = int(msg.text.split(maxsplit=1)[1]) - 1
        if 0 <= index < len(questions_morning):
            removed = questions_morning.pop(index)
            await msg.reply_text(f"✅ Removed morning question:\n{removed}")
        else:
            await msg.reply_text("❌ Invalid index. Use /listquestions to see indices.")
    except (ValueError, IndexError):
        await msg.reply_text("Usage: /removemq <index>")

@bot.on_message(filters.command("removeeq") & filters.user(MY_USER_ID))
async def remove_evening_question(client: Client, msg: Message):
    """Remove an evening question by index"""
    try:
        index = int(msg.text.split(maxsplit=1)[1]) - 1
        if 0 <= index < len(questions_evening):
            removed = questions_evening.pop(index)
            await msg.reply_text(f"✅ Removed evening question:\n{removed}")
        else:
            await msg.reply_text("❌ Invalid index. Use /listquestions to see indices.")
    except (ValueError, IndexError):
        await msg.reply_text("Usage: /removeeq <index>")

@bot.on_message(filters.command("setmorningcount") & filters.user(MY_USER_ID))
async def set_morning_count(client: Client, msg: Message):
    """Set how many morning questions to send"""
    try:
        count = int(msg.text.split(maxsplit=1)[1])
        if count <= 0:
            await msg.reply_text("❌ Count must be at least 1")
            return
        
        global morning_question_count
        morning_question_count = min(count, 5)  # Limit to 5 questions max
        await msg.reply_text(f"✅ Morning question count set to {morning_question_count}")
    except (ValueError, IndexError):
        await msg.reply_text("Usage: /setmorningcount <number>")

@bot.on_message(filters.command("seteveningcount") & filters.user(MY_USER_ID))
async def set_evening_count(client: Client, msg: Message):
    """Set how many evening questions to send"""
    try:
        count = int(msg.text.split(maxsplit=1)[1])
        if count <= 0:
            await msg.reply_text("❌ Count must be at least 1")
            return
        
        global evening_question_count
        evening_question_count = min(count, 5)  # Limit to 5 questions max
        await msg.reply_text(f"✅ Evening question count set to {evening_question_count}")
    except (ValueError, IndexError):
        await msg.reply_text("Usage: /seteveningcount <number>")

@bot.on_message(filters.command("setmorningtime") & filters.user(MY_USER_ID))
async def set_morning_time(client: Client, msg: Message):
    """Set the time to send morning questions"""
    try:
        time_str = msg.text.split(maxsplit=1)[1]
        hour, minute = parse_time(time_str)
        
        global morning_question_time
        morning_question_time = f"{hour:02d}:{minute:02d}"
        
        reschedule_job("send_morning_question", hour, minute)
        await msg.reply_text(f"✅ Morning question time set to {morning_question_time} (Asia/Kolkata)")
    except (ValueError, IndexError) as e:
        await msg.reply_text(f"❌ {str(e)}\nUsage: /setmorningtime HH:MM (24-hour format)")

@bot.on_message(filters.command("seteveningtime") & filters.user(MY_USER_ID))
async def set_evening_time(client: Client, msg: Message):
    """Set the time to send evening questions"""
    try:
        time_str = msg.text.split(maxsplit=1)[1]
        hour, minute = parse_time(time_str)
        
        global evening_question_time
        evening_question_time = f"{hour:02d}:{minute:02d}"
        
        reschedule_job("send_evening_question", hour, minute)
        await msg.reply_text(f"✅ Evening question time set to {evening_question_time} (Asia/Kolkata)")
    except (ValueError, IndexError) as e:
        await msg.reply_text(f"❌ {str(e)}\nUsage: /seteveningtime HH:MM (24-hour format)")

@bot.on_message(filters.command("questionstatus") & filters.user(MY_USER_ID))
async def question_status(client: Client, msg: Message):
    """Show current question settings"""
    status_text = (
        "📊 Question Settings:\n\n"
        f"🌅 Morning:\n"
        f"Time: {morning_question_time}\n"
        f"Count: {morning_question_count}\n"
        f"Questions in pool: {len(questions_morning)}\n\n"
        f"🌇 Evening:\n"
        f"Time: {evening_question_time}\n"
        f"Count: {evening_question_count}\n"
        f"Questions in pool: {len(questions_evening)}"
    )
    await msg.reply_text(status_text)

# --- Fill in the Blanks Handlers ---
@bot.on_message(filters.command("dailyq"))
async def daily_question_handler(client: Client, msg: Message):
    """Send current daily questions or status"""
    if msg.from_user.id not in [BESTIE_USER_ID, MY_USER_ID]:
        await msg.reply_text("This feature is only available for special users! 💖")
        return
    
    today = datetime.date.today()
    
    # Check morning question
    if current_morning_question["date"] != today or not current_morning_question["question"]:
        new_question = get_new_morning_question()
        current_morning_question["question"] = new_question
        current_morning_question["date"] = today
        current_morning_question["answered"] = False
    
    # Check evening question
    if current_evening_question["date"] != today or not current_evening_question["question"]:
        new_question = get_new_evening_question()
        current_evening_question["question"] = new_question
        current_evening_question["date"] = today
        current_evening_question["answered"] = False
    
    if msg.from_user.id == BESTIE_USER_ID:
        morning_status = "✅ Answered" if current_morning_question["answered"] else "⏳ Waiting for answer"
        evening_status = "✅ Answered" if current_evening_question["answered"] else "⏳ Waiting for answer"
        
        await msg.reply_text(
            f"📝 Today's Questions:\n\n"
            f"🌅 Morning:\n{current_morning_question['question']}\n"
            f"Status: {morning_status}\n\n"
            f"🌇 Evening:\n{current_evening_question['question']}\n"
            f"Status: {evening_status}\n\n"
            f"💡 Just reply with your answers!"
        )
    else:  # MY_USER_ID
        morning_status = "✅ Received" if current_morning_question["answered"] else "⏳ Waiting"
        evening_status = "✅ Received" if current_evening_question["answered"] else "⏳ Waiting"
        
        await msg.reply_text(
            f"📊 Daily Questions Status:\n\n"
            f"🌅 Morning:\n{current_morning_question['question']}\n"
            f"Status: {morning_status}\n\n"
            f"🌇 Evening:\n{current_evening_question['question']}\n"
            f"Status: {evening_status}"
        )

@bot.on_message(filters.private & filters.user(BESTIE_USER_ID) & ~filters.command(["start", "quote", "photo", "vibe", "music", "id", "dailyq"]))
async def handle_bestie_answer(client: Client, msg: Message):
    """Handle answers from bestie user for both morning and evening questions"""
    today = datetime.date.today()
    response_sent = False
    
    # Check morning question
    if (current_morning_question["date"] == today and 
        current_morning_question["question"] and 
        not current_morning_question["answered"]):
        
        # Mark as answered
        current_morning_question["answered"] = True
        
        # Send answer to MY_USER_ID
        answer_text = (
            f"🌅 Morning Question Answer 🌅\n\n"
            f"📝 Question: {current_morning_question['question']}\n\n"
            f"💬 Answer: {msg.text}\n\n"
            f"📅 Date: {today.strftime('%B %d, %Y')}"
        )
        
        await bot.send_message(MY_USER_ID, answer_text)
        
        # Confirm to bestie
        await msg.reply_text(
            "✅ Your morning answer has been sent! 💖\n"
            "Thank you for sharing your thoughts! 🌟"
        )
        response_sent = True
    
    # Check evening question
    if (current_evening_question["date"] == today and 
        current_evening_question["question"] and 
        not current_evening_question["answered"] and
        not response_sent):
        
        # Mark as answered
        current_evening_question["answered"] = True
        
        # Send answer to MY_USER_ID
        answer_text = (
            f"🌇 Evening Question Answer 🌇\n\n"
            f"📝 Question: {current_evening_question['question']}\n\n"
            f"💬 Answer: {msg.text}\n\n"
            f"📅 Date: {today.strftime('%B %d, %Y')}"
        )
        
        await bot.send_message(MY_USER_ID, answer_text)
        
        # Confirm to bestie
        await msg.reply_text(
            "✅ Your evening answer has been sent! 💖\n"
            "Thank you for sharing your thoughts! 🌟"
        )
        response_sent = True
    
    if not response_sent:
        # Regular message handling
        await msg.reply_text("Hey there! 💖 Use /dailyq to see today's questions!")

# --- Code Management System ---
async def get_current_code() -> str:
    with open(CODE_FILE, "r") as f:
        return f.read()

async def save_new_code(code: str) -> bool:
    if os.path.exists(CODE_FILE):
        os.rename(CODE_FILE, BACKUP_FILE)
    
    with open(CODE_FILE, "w") as f:
        f.write(code)
    
    return True

async def restart_bot():
    os.execv(sys.executable, [sys.executable] + sys.argv)

@bot.on_message(filters.command("getcode") & filters.user(MY_USER_ID))
async def send_code_handler(client: Client, msg: Message):
    try:
        code = await get_current_code()
        with StringIO(code) as file:
            file.name = CODE_FILE
            await msg.reply_document(
                document=file,
                caption="📄 Current bot code",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Edit Code", callback_data="edit_code")]
                ])
            )
    except Exception as e:
        await msg.reply_text(f"❌ Failed to get code: {str(e)}")

@bot.on_message(filters.command("updatecode") & filters.user(MY_USER_ID))
async def update_code_handler(client: Client, msg: Message):
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text("❌ Please reply to a document containing the new code")
        return
    
    try:
        file_path = await msg.reply_to_message.download()
        
        with open(file_path, "r") as f:
            new_code = f.read()
        
        success = await save_new_code(new_code)
        
        if success:
            await msg.reply_text(
                "✅ Code updated successfully!\n"
                "Do you want to restart the bot to apply changes?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Restart Now", callback_data="confirm_restart")],
                    [InlineKeyboardButton("🚫 Cancel", callback_data="cancel_restart")]
                ])
            )
        else:
            await msg.reply_text("❌ Failed to save new code")
        
        os.remove(file_path)
        
    except Exception as e:
        await msg.reply_text(f"❌ Update failed: {str(e)}")

@bot.on_callback_query(filters.regex("edit_code") & filters.user(MY_USER_ID))
async def edit_code_callback(client: Client, cq: CallbackQuery):
    try:
        code = await get_current_code()
        await cq.message.reply_text(
            f"✏️ Current code (edit and send back with /updatecode):\n\n"
            f"```python\n{code[:4000]}```\n\n"
            f"[...] (full code sent as file)",
            parse_mode="markdown"
        )
        await cq.answer()
    except Exception as e:
        await cq.message.reply_text(f"❌ Error: {str(e)}")
        await cq.answer()

@bot.on_callback_query(filters.regex("confirm_restart") & filters.user(MY_USER_ID))
async def confirm_restart_callback(client: Client, cq: CallbackQuery):
    await cq.message.edit_text("🔄 Restarting bot...")
    await cq.answer()
    await restart_bot()

@bot.on_callback_query(filters.regex("cancel_restart") & filters.user(MY_USER_ID))
async def cancel_restart_callback(client: Client, cq: CallbackQuery):
    await cq.message.edit_text("🚫 Restart cancelled. Changes will take effect after next restart.")
    await cq.answer()

# --- Game Handlers ---
@bot.on_message(filters.command("ttt"))
async def ttt_handler(client: Client, msg: Message):
    uid = msg.from_user.id
    board = [" "] * 9
    games[uid] = board
    await msg.reply_text(
        "Your turn! You're ❌ (X).\n\n" + render_board_text(board),
        reply_markup=build_board_keyboard(board)
    )

@bot.on_callback_query(filters.regex(r"ttt_(\d)"))
async def ttt_callback(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    idx = int(cq.data.split("_")[1])
    
    if uid not in games or games[uid][idx] != " ":
        await cq.answer("Invalid move", show_alert=True)
        return
    
    games[uid][idx] = "X"
    
    if check_winner(games[uid], "X"):
        await cq.message.edit_text(
            render_board_text(games[uid]) + "\n\nYou won! 🎉"
        )
        del games[uid]
        await cq.answer()
        return
    
    if is_board_full(games[uid]):
        await cq.message.edit_text(
            render_board_text(games[uid]) + "\n\nDraw!"
        )
        del games[uid]
        await cq.answer()
        return
    
    bot_idx = bot_move(games[uid])
    if bot_idx is not None:
        games[uid][bot_idx] = "O"
        if check_winner(games[uid], "O"):
            await cq.message.edit_text(
                render_board_text(games[uid]) + "\n\nI won! 😎"
            )
            del games[uid]
            await cq.answer()
            return
        
        if is_board_full(games[uid]):
            await cq.message.edit_text(
                render_board_text(games[uid]) + "\n\nDraw!"
            )
            del games[uid]
            await cq.answer()
            return
    
    await cq.message.edit_text(
        "Your turn! You're ❌ (X).\n\n" + render_board_text(games[uid]),
        reply_markup=build_board_keyboard(games[uid])
    )
    await cq.answer()

# --- Multiplayer Game Handlers ---
@bot.on_message(filters.command("onlinettt"))
async def online_ttt_handler(client: Client, msg: Message):
    user_id = msg.from_user.id
    
    if user_id in waiting_queue:
        await msg.reply_text("❌ You're already in the queue! Use /cancelqueue to leave.")
        return
    
    if waiting_queue and waiting_queue[0] != user_id:
        x_id, o_id = waiting_queue.pop(0), user_id
        board = [" "] * 9
        markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}")
        board_text = render_board_text(board)
        
        m1 = await bot.send_message(
            x_id,
            f"🎮 Multiplayer started! You're ❌\n\n{board_text}",
            reply_markup=markup
        )
        m2 = await bot.send_message(
            o_id,
            f"🎮 Multiplayer started! You're ⚫\nWaiting for ❌\n\n{board_text}",
            reply_markup=markup
        )
        
        online_games[(x_id, o_id)] = {
            "board": board,
            "messages": {x_id: m1, o_id: m2}
        }
    else:
        waiting_queue.append(user_id)
        cancel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel Queue", callback_data="cancel_queue")]
        ])
        await msg.reply_text(
            "⏳ You're in the queue. Waiting for an opponent...\n"
            "Use /cancelqueue or the button below to leave the queue.",
            reply_markup=cancel_markup
        )

@bot.on_message(filters.command("cancelqueue"))
async def cancel_queue_handler(client: Client, msg: Message):
    user_id = msg.from_user.id
    if user_id in waiting_queue:
        waiting_queue.remove(user_id)
        await msg.reply_text("✅ You've been removed from the queue.")
    else:
        await msg.reply_text("❌ You're not in the queue.")

@bot.on_callback_query(filters.regex("cancel_queue"))
async def cancel_queue_callback(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    if user_id in waiting_queue:
        waiting_queue.remove(user_id)
        await cq.message.edit_text("✅ You've been removed from the queue.")
    else:
        await cq.answer("You're not in the queue.", show_alert=True)
    await cq.answer()

@bot.on_callback_query(filters.regex(r"multi_(\d+)_(\d+)_(\d+)"))
async def multiplayer_move_handler(client: Client, cq: CallbackQuery):
    x_id, o_id, move = map(int, cq.data.split("_")[1:])
    uid = cq.from_user.id
    game_key = (x_id, o_id)
    
    if game_key not in online_games:
        await cq.answer("Game not found", show_alert=True)
        return
    
    game = online_games[game_key]
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

    async def edit_msg(msg_obj, txt):
        await msg_obj.edit_text(txt, reply_markup=markup)
    
    m1, m2 = game["messages"][x_id], game["messages"][o_id]

    if check_winner(board, turn):
        del online_games[game_key]
        rematch_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Rematch", callback_data=f"rematch_{x_id}_{o_id}")]
        ])
        await edit_msg(m1, f"{text}\n\n{turn} wins!")
        await edit_msg(m2, f"{text}\n\n{turn} wins!")
        await bot.send_message(x_id, "Ask for rematch 🔁", reply_markup=rematch_markup)
        await bot.send_message(o_id, "Ask for rematch 🔁", reply_markup=rematch_markup)
    elif is_board_full(board):
        del online_games[game_key]
        await edit_msg(m1, f"{text}\n\nDraw!")
        await edit_msg(m2, f"{text}\n\nDraw!")
    else:
        await edit_msg(m1, text)
        await edit_msg(m2, text)
    
    await cq.answer()

@bot.on_callback_query(filters.regex(r"rematch_(\d+)_(\d+)"))
async def rematch_request_handler(client: Client, cq: CallbackQuery):
    x_id, o_id = map(int, cq.data.split("_")[1:])
    sender = cq.from_user.id
    key = tuple(sorted([x_id, o_id]))
    
    rematch_requests.setdefault(key, set()).add(sender)
    
    if len(rematch_requests[key]) == 2:
        del rematch_requests[key]
        board = [" "] * 9
        markup = build_board_keyboard(board, prefix=f"multi_{x_id}_{o_id}")
        txt = render_board_text(board)
        
        m1 = await bot.send_message(
            x_id,
            f"🔁 Rematch started! You're ❌\n\n{txt}",
            reply_markup=markup
        )
        m2 = await bot.send_message(
            o_id,
            f"🔁 Rematch started! You're ⚫\n\n{txt}",
            reply_markup=markup
        )
        
        online_games[(x_id, o_id)] = {
            "board": board,
            "messages": {x_id: m1, o_id: m2}
        }
    else:
        await cq.answer("Rematch request sent. Waiting for opponent.", show_alert=True)

# --- In-Game Chat ---
@bot.on_message(filters.command("say") & filters.private)
async def say_handler(client: Client, msg: Message):
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

# --- Greeting Management ---
@bot.on_message(filters.command("setmorning") & filters.user(MY_USER_ID))
async def set_morning_handler(client: Client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setmorning Your new morning message")
        return
    
    greetings["morning"] = parts[1]
    await msg.reply_text(f"✅ Morning greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("setafternoon") & filters.user(MY_USER_ID))
async def set_afternoon_handler(client: Client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setafternoon Your new afternoon message")
        return
    
    greetings["afternoon"] = parts[1]
    await msg.reply_text(f"✅ Afternoon greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("setnight") & filters.user(MY_USER_ID))
async def set_night_handler(client: Client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setnight Your new night message")
        return
    
    greetings["night"] = parts[1]
    await msg.reply_text(f"✅ Night greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("listgreetings") & filters.user(MY_USER_ID))
async def list_greetings_handler(client: Client, msg: Message):
    greeting_text = (
        "🌅 Morning:\n" + greetings["morning"] + "\n\n"
        "🌞 Afternoon:\n" + greetings["afternoon"] + "\n\n"
        "🌙 Night:\n" + greetings["night"]
    )
    await msg.reply_text(greeting_text)

# --- Scheduled Greetings ---
async def send_morning_greeting():
    """Send morning greeting to bestie user"""
    await bot.send_message(BESTIE_USER_ID, greetings["morning"])

async def send_afternoon_greeting():
    """Send afternoon greeting to bestie user"""
    await bot.send_message(BESTIE_USER_ID, greetings["afternoon"])

async def send_night_greeting():
    """Send night greeting to bestie user"""
    await bot.send_message(BESTIE_USER_ID, greetings["night"])

# --- Scheduled Greeting Management ---
@bot.on_message(filters.command("setgreetingtime") & filters.user(MY_USER_ID))
async def set_greeting_time_handler(client: Client, msg: Message):
    """Set greeting times (morning, afternoon, night)"""
    try:
        parts = msg.text.split(maxsplit=2)
        if len(parts) != 3:
            raise ValueError("Usage: /setgreetingtime <morning|afternoon|night> HH:MM")
        
        greeting_type = parts[1].lower()
        if greeting_type not in ["morning", "afternoon", "night"]:
            raise ValueError("Invalid greeting type. Use morning/afternoon/night")
        
        hour, minute = parse_time(parts[2])
        time_str = f"{hour:02d}:{minute:02d}"
        
        job_id = f"send_{greeting_type}_greeting"
        reschedule_job(job_id, hour, minute)
        
        await msg.reply_text(f"✅ {greeting_type.capitalize()} greeting time set to {time_str} (Asia/Kolkata)")
    except Exception as e:
        await msg.reply_text(f"❌ {str(e)}")

# --- Random Quote Handler ---
@bot.on_message(filters.command("quote") & filters.user(BESTIE_USER_ID))
async def send_random_quote(client: Client, msg: Message):
    """Send a random quote to bestie"""
    quote = random.choice(quotes)
    await msg.reply_text(quote)

# --- Quote Management ---
@bot.on_message(filters.command("addquote") & filters.user(MY_USER_ID))
async def add_quote_handler(client: Client, msg: Message):
    """Add a new quote to the pool"""
    quote = msg.text.split(maxsplit=1)
    if len(quote) < 2:
        await msg.reply_text("Usage: /addquote <your quote>")
        return
    
    quotes.append(quote[1])
    await msg.reply_text(f"✅ Added quote:\n{quote[1]}")

@bot.on_message(filters.command("removequote") & filters.user(MY_USER_ID))
async def remove_quote_handler(client: Client, msg: Message):
    """Remove a quote by index"""
    try:
        index = int(msg.text.split(maxsplit=1)[1]) - 1
        if 0 <= index < len(quotes):
            removed = quotes.pop(index)
            await msg.reply_text(f"✅ Removed quote:\n{removed}")
        else:
            await msg.reply_text("❌ Invalid index. Use /listquotes to see indices.")
    except (ValueError, IndexError):
        await msg.reply_text("Usage: /removequote <index>")

@bot.on_message(filters.command("listquotes") & filters.user(MY_USER_ID))
async def list_quotes_handler(client: Client, msg: Message):
    """List all quotes with indices"""
    quotes_text = "📜 Quotes:\n" + "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(quotes)
    ) if quotes else "No quotes yet!"
    await msg.reply_text(quotes_text)

# --- Photo Sharing ---
@bot.on_message(filters.command("photo") & filters.user(BESTIE_USER_ID))
async def send_random_photo(client: Client, msg: Message):
    """Send a random photo from the photo folder"""
    try:
        photos = [f for f in os.listdir(PHOTO_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if not photos:
            await msg.reply_text("No photos available in the photo folder!")
            return
        
        photo_path = os.path.join(PHOTO_FOLDER, random.choice(photos))
        await msg.reply_photo(photo=photo_path)
    except Exception as e:
        await msg.reply_text(f"❌ Failed to send photo: {str(e)}")

# --- Music Sharing ---
@bot.on_message(filters.command("music") & filters.user(BESTIE_USER_ID))
async def send_random_music(client: Client, msg: Message):
    """Send a random music file from the music folder"""
    try:
        songs = [f for f in os.listdir(SONG_FOLDER) if f.lower().endswith(('.mp3', '.ogg', '.wav'))]
        if not songs:
            await msg.reply_text("No songs available in the music folder!")
            return
        
        song_path = os.path.join(SONG_FOLDER, random.choice(songs))
        await msg.reply_audio(audio=song_path)
    except Exception as e:
        await msg.reply_text(f"❌ Failed to send music: {str(e)}")

# --- User ID Command ---
@bot.on_message(filters.command("id"))
async def get_user_id(client: Client, msg: Message):
    """Get user ID"""
    await msg.reply_text(f"Your user ID: {msg.from_user.id}")

# --- Command Access Levels ---
@bot.on_message(filters.command("start"))
async def start_command(client: Client, msg: Message):
    """Welcome message with user-specific information and commands"""
    user_id = msg.from_user.id
    
    if user_id == MY_USER_ID:  # Admin
        welcome_text = """
👑 *Admin Panel*

Welcome back! Here are your available commands:

🛠️ *Admin Commands*:

*Daily Questions:*
/addmorningq <question> - Add morning question
/addeveningq <question> - Add evening question
/listquestions - List all questions
/removemq <index> - Remove morning question
/removeeq <index> - Remove evening question
/setmorningcount <number> - Set morning question count
/seteveningcount <number> - Set evening question count
/setmorningtime HH:MM - Set morning question time
/seteveningtime HH:MM - Set evening question time
/questionstatus - Show question settings

*Greetings:*
/setmorning <text> - Set morning greeting
/setafternoon <text> - Set afternoon greeting
/setnight <text> - Set night greeting
/listgreetings - List current greetings
/setgreetingtime <type> HH:MM - Set greeting time

*Quotes:*
/addquote <text> - Add new quote
/removequote <index> - Remove quote
/listquotes - List all quotes

*System:*
/restart - Restart the bot
/id - Show your user ID
"""
    elif user_id == BESTIE_USER_ID:  # Bestie
        welcome_text = f"""
💖 *Welcome Bestie!* 💖

Here's what I can do for you:

💖 *Bestie Commands*:
/dailyq - See today's questions
/quote - Get random sweet message
/photo - Get random photo
/music - Get random song
/id - Show your user ID

🎮 *Games*:
/ttt - Play Tic-Tac-Toe vs bot
/onlinettt - Play Tic-Tac-Toe vs friend
/cancelqueue - Leave matchmaking queue
/say <message> - Send message to opponent
"""
    else:  # Normal user
        welcome_text = """
👋 *Welcome!*

Available Commands:
/id - Show your user ID
/ttt - Play Tic-Tac-Toe vs bot
/onlinettt - Play Tic-Tac-Toe vs friend
/cancelqueue - Leave matchmaking queue
/say <message> - Send message to opponent
"""

    await msg.reply_text(welcome_text.strip(), parse_mode="markdown")

# --- Admin-only Commands ---
@bot.on_message(filters.command("restart") & filters.user(MY_USER_ID))
async def restart_command(client: Client, msg: Message):
    """Restart the bot (admin only)"""
    await msg.reply_text("🔄 Restarting bot...")
    await restart_bot()

# --- Bestie-only Commands ---
@bot.on_message(filters.command(["photo", "music", "quote"]) & ~filters.user(BESTIE_USER_ID))
async def bestie_only_commands(client: Client, msg: Message):
    """Handle unauthorized access to bestie-only commands"""
    await msg.reply_text("This feature is only available for special users! 💖")

# --- Update the handle_bestie_answer function to include command filtering ---
@bot.on_message(filters.private & filters.user(BESTIE_USER_ID) & ~filters.command())
async def handle_bestie_answer(client: Client, msg: Message):
    """Handle answers from bestie user for both morning and evening questions"""
    # ... (keep existing implementation from earlier)

# --- Startup and Shutdown ---
@app.on_event("startup")
async def startup():
    await bot.start()
    scheduler.start()
    
    # Schedule greetings
    morning_hour, morning_minute = parse_time("06:00")
    afternoon_hour, afternoon_minute = parse_time("12:00")
    night_hour, night_minute = parse_time("22:00")
    
    scheduler.add_job(
        send_morning_greeting,
        'cron',
        hour=morning_hour,
        minute=morning_minute,
        id="send_morning_greeting"
    )
    
    scheduler.add_job(
        send_afternoon_greeting,
        'cron',
        hour=afternoon_hour,
        minute=afternoon_minute,
        id="send_afternoon_greeting"
    )
    
    scheduler.add_job(
        send_night_greeting,
        'cron',
        hour=night_hour,
        minute=night_minute,
        id="send_night_greeting"
    )
    
    # Schedule daily questions
    morning_q_hour, morning_q_minute = parse_time(morning_question_time)
    evening_q_hour, evening_q_minute = parse_time(evening_question_time)
    
    scheduler.add_job(
        send_morning_question,
        'cron',
        hour=morning_q_hour,
        minute=morning_q_minute,
        id="send_morning_question"
    )
    
    scheduler.add_job(
        send_evening_question,
        'cron',
        hour=evening_q_hour,
        minute=evening_q_minute,
        id="send_evening_question"
    )

@app.on_event("shutdown")
async def shutdown():
    await bot.stop()

# --- Webhook Handler ---
@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        update = await request.json()
        update = Update(**update)
        await bot.process_update(update)
        return PlainTextResponse("OK")
    except Exception as e:
        return PlainTextResponse(f"Error: {str(e)}", status_code=500)

# --- Main Entry Point ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
