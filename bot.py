# --- Imports ---
import os
import random
import asyncio
import pytz
import httpx
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Dict, List, Tuple, Optional, Set

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
MY_USER_ID = 7590978422

# --- Content Pools ---
quotes = [
    "You're not just a star, you're my whole sky. ✨",
    "Your smile makes my day every time 😊",
    "You're the kindest soul I've ever met 💖",
    "Just a reminder: You're amazing. No doubt. 💫"
]

# --- Customizable Greetings ---
greetings = {
    "morning": "🌞 Good morning bestie have a nice day! 💖",
    "afternoon": "🌞 Good Afternoon Kritika Eat well! 💖🎶",
    "night": "🌙 Good night Dumb Jigs I Like u the most 💫"
}

# --- Media Management ---
photo_folder = "photos"
song_folder = "songs"

# Create folders if they don't exist
os.makedirs(photo_folder, exist_ok=True)
os.makedirs(song_folder, exist_ok=True)

def get_photo_files() -> List[str]:
    return [os.path.join(photo_folder, f) for f in os.listdir(photo_folder) 
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]

def get_song_files() -> List[str]:
    return [os.path.join(song_folder, f) for f in os.listdir(song_folder) 
            if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.ogg'))]

# Track upload mode for MY_USER_ID
upload_mode = {"photo": False, "song": False}

# --- Game Constants ---
SUITS = ["♠️", "♥️", "♦️", "♣️"]
VALUES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# --- Tic-Tac-Toe Game Implementation ---
class TicTacToeGame:
    def __init__(self, player1_id: int, player2_id: Optional[int] = None):
        self.board = [[" " for _ in range(3)] for _ in range(3)]
        self.players = [player1_id, player2_id] if player2_id else [player1_id]
        self.current_player = 0
        self.game_over = False
        self.winner = None
        self.message_obj = None
        self.is_online = player2_id is not None
    
    def make_move(self, row: int, col: int) -> bool:
        if self.game_over or row < 0 or row > 2 or col < 0 or col > 2 or self.board[row][col] != " ":
            return False
        
        symbol = "X" if self.current_player == 0 else "O"
        self.board[row][col] = symbol
        
        if self.check_winner(symbol):
            self.game_over = True
            self.winner = self.players[self.current_player]
        elif self.is_board_full():
            self.game_over = True
        else:
            self.current_player = 1 - self.current_player
        
        return True
    
    def check_winner(self, symbol: str) -> bool:
        # Check rows
        for row in self.board:
            if all(cell == symbol for cell in row):
                return True
        
        # Check columns
        for col in range(3):
            if all(self.board[row][col] == symbol for row in range(3)):
                return True
        
        # Check diagonals
        if all(self.board[i][i] == symbol for i in range(3)):
            return True
        if all(self.board[i][2-i] == symbol for i in range(3)):
            return True
        
        return False
    
    def is_board_full(self) -> bool:
        return all(cell != " " for row in self.board for cell in row)
    
    def render_board(self) -> str:
        board_str = "🅇 Tic-Tac-Toe 🅇\n\n"
        for row in self.board:
            board_str += " | ".join(cell if cell != " " else "⬜️" for cell in row) + "\n"
            board_str += "---------\n"
        
        if self.game_over:
            if self.winner:
                board_str += f"\n🎉 Player {self.players.index(self.winner)+1} wins! 🎉"
            else:
                board_str += "\n🤝 It's a draw! 🤝"
        else:
            player_num = self.current_player + 1
            board_str += f"\nPlayer {player_num}'s turn ({'X' if self.current_player == 0 else 'O'})"
        
        return board_str
    
    def build_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = []
        for row in range(3):
            keyboard_row = []
            for col in range(3):
                cell = self.board[row][col]
                if cell == " ":
                    text = "⬜️"
                    callback_data = f"ttt_move_{row}_{col}"
                else:
                    text = "❌" if cell == "X" else "⭕️"
                    callback_data = "ttt_invalid"
                keyboard_row.append(InlineKeyboardButton(text, callback_data=callback_data))
            keyboard.append(keyboard_row)
        
        if self.game_over:
            keyboard.append([InlineKeyboardButton("🔄 New Game", callback_data="ttt_new")])
        keyboard.append([InlineKeyboardButton("❌ Quit", callback_data="ttt_quit")])
        
        return InlineKeyboardMarkup(keyboard)

# --- Game State Management ---
solitaire_games: Dict[int, SolitaireGame] = {}
ttt_games: Dict[int, TicTacToeGame] = {}  # Single player games
online_ttt_games: Dict[str, TicTacToeGame] = {}  # Multiplayer games
ttt_waiting_queue: List[int] = []

# --- Media Upload Handlers (Admin Only) ---
@bot.on_message(filters.command("addphoto") & filters.user(MY_USER_ID))
async def add_photo_mode_handler(client, msg: Message):
    upload_mode["photo"] = True
    upload_mode["song"] = False
    await msg.reply_text(
        "📸 Photo Upload Mode ON!\n\n"
        "Send me photos to add to the collection.\n"
        "Use /done when finished or /cancel to stop."
    )

@bot.on_message(filters.command("addsong") & filters.user(MY_USER_ID))
async def add_song_mode_handler(client, msg: Message):
    upload_mode["song"] = True
    upload_mode["photo"] = False
    await msg.reply_text(
        "🎵 Song Upload Mode ON!\n\n"
        "Send me audio files to add to the collection.\n"
        "Use /done when finished or /cancel to stop."
    )

@bot.on_message(filters.command(["done", "cancel"]) & filters.user(MY_USER_ID))
async def upload_done_handler(client, msg: Message):
    was_active = upload_mode["photo"] or upload_mode["song"]
    upload_mode["photo"] = False
    upload_mode["song"] = False
    await msg.reply_text("✅ Upload mode disabled!" if was_active else "ℹ️ No upload mode was active.")

@bot.on_message(filters.photo & filters.user(MY_USER_ID))
async def handle_photo_upload(client, msg: Message):
    if not upload_mode["photo"]:
        return
    
    try:
        file_id = msg.photo.file_id
        filename = f"photo_{file_id[:10]}_{random.randint(1000, 9999)}.jpg"
        file_path = os.path.join(photo_folder, filename)
        await msg.download(file_name=file_path)
        await msg.reply_text(f"✅ Photo saved as: {filename}")
    except Exception as e:
        await msg.reply_text(f"❌ Error saving photo: {str(e)}")

@bot.on_message(filters.audio & filters.user(MY_USER_ID))
async def handle_audio_upload(client, msg: Message):
    if not upload_mode["song"]:
        return
    
    try:
        audio = msg.audio
        filename = audio.file_name or f"{audio.performer or 'Unknown'} - {audio.title or 'Unknown'}_{random.randint(1000, 9999)}.mp3"
        filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
        file_path = os.path.join(song_folder, filename)
        await msg.download(file_name=file_path)
        
        duration = f"{audio.duration // 60}:{audio.duration % 60:02d}" if audio.duration else "Unknown"
        await msg.reply_text(
            f"✅ Song saved!\n📁 Filename: {filename}\n⏱️ Duration: {duration}"
        )
    except Exception as e:
        await msg.reply_text(f"❌ Error saving song: {str(e)}")

@bot.on_message(filters.document & filters.user(MY_USER_ID))
async def handle_document_upload(client, msg: Message):
    if not upload_mode["song"]:
        return
    
    doc = msg.document
    if not doc.file_name or not doc.file_name.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac')):
        await msg.reply_text("⚠️ Please send only audio files when in song upload mode.")
        return
    
    try:
        filename = doc.file_name
        file_path = os.path.join(song_folder, filename)
        
        if os.path.exists(file_path):
            base, ext = os.path.splitext(filename)
            filename = f"{base}_{random.randint(1000, 9999)}{ext}"
            file_path = os.path.join(song_folder, filename)
        
        await msg.download(file_name=file_path)
        file_size = f"{doc.file_size / (1024*1024):.1f} MB" if doc.file_size else "Unknown size"
        await msg.reply_text(
            f"✅ Audio file saved!\n📁 Filename: {filename}\n📊 Size: {file_size}"
        )
    except Exception as e:
        await msg.reply_text(f"❌ Error saving audio file: {str(e)}")

# --- Media Management Commands (Admin Only) ---
@bot.on_message(filters.command("listmedia") & filters.user(MY_USER_ID))
async def list_media_handler(client, msg: Message):
    photos = get_photo_files()
    songs = get_song_files()
    
    response = "📂 Media Collection:\n\n"
    response += f"📸 Photos: {len(photos)} files\n"
    if photos:
        response += "• " + "\n• ".join(os.path.basename(p) for p in photos[:5])
        if len(photos) > 5:
            response += f"\n• ... and {len(photos)-5} more"
    
    response += "\n\n🎵 Songs: {len(songs)} files\n"
    if songs:
        response += "• " + "\n• ".join(os.path.basename(s) for s in songs[:5])
        if len(songs) > 5:
            response += f"\n• ... and {len(songs)-5} more"
    
    if not photos and not songs:
        response += "Empty collection. Use /addphoto or /addsong to add media!"
    
    await msg.reply_text(response)

@bot.on_message(filters.command("clearmedia") & filters.user(MY_USER_ID))
async def clear_media_handler(client, msg: Message):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Clear Photos", callback_data="clear_photos"),
            InlineKeyboardButton("🎵 Clear Songs", callback_data="clear_songs")
        ],
        [InlineKeyboardButton("🗑️ Clear All Media", callback_data="clear_all_media")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_clear")]
    ])
    
    await msg.reply_text(
        f"🗑️ Clear Media Collection\n\n"
        f"📸 Photos: {len(get_photo_files())} files\n"
        f"🎵 Songs: {len(get_song_files())} files\n\n"
        f"⚠️ Warning: This action cannot be undone!",
        reply_markup=keyboard
    )

@bot.on_callback_query(filters.regex("clear_photos") & filters.user(MY_USER_ID))
async def clear_photos_callback(client, cq):
    try:
        photos = get_photo_files()
        for photo in photos:
            os.remove(photo)
        await cq.message.edit_text(f"✅ Cleared {len(photos)} photos!")
    except Exception as e:
        await cq.message.edit_text(f"❌ Error clearing photos: {str(e)}")
    await cq.answer()

@bot.on_callback_query(filters.regex("clear_songs") & filters.user(MY_USER_ID))
async def clear_songs_callback(client, cq):
    try:
        songs = get_song_files()
        for song in songs:
            os.remove(song)
        await cq.message.edit_text(f"✅ Cleared {len(songs)} songs!")
    except Exception as e:
        await cq.message.edit_text(f"❌ Error clearing songs: {str(e)}")
    await cq.answer()

@bot.on_callback_query(filters.regex("clear_all_media") & filters.user(MY_USER_ID))
async def clear_all_media_callback(client, cq):
    try:
        photos = get_photo_files()
        songs = get_song_files()
        for photo in photos:
            os.remove(photo)
        for song in songs:
            os.remove(song)
        total = len(photos) + len(songs)
        await cq.message.edit_text(f"✅ Cleared all media! ({total} files removed)")
    except Exception as e:
        await cq.message.edit_text(f"❌ Error clearing media: {str(e)}")
    await cq.answer()

@bot.on_callback_query(filters.regex("cancel_clear"))
async def cancel_clear_callback(client, cq):
    await cq.message.edit_text("❌ Clear operation cancelled.")
    await cq.answer()

# --- Solitaire Handlers ---
@bot.on_message(filters.command("solitaire"))
async def solitaire_handler(client, msg: Message):
    user_id = msg.from_user.id
    
    if user_id in solitaire_games:
        game = solitaire_games[user_id]
        try:
            await game.message_obj.edit_text(
                game.render_game(),
                reply_markup=game.build_keyboard()
            )
        except:
            game.message_obj = await msg.reply_text(
                game.render_game(),
                reply_markup=game.build_keyboard()
            )
        return
    
    game = SolitaireGame(user_id)
    solitaire_games[user_id] = game
    game.message_obj = await msg.reply_text(
        game.render_game(),
        reply_markup=game.build_keyboard()
    )

@bot.on_callback_query(filters.regex(r"^solitaire_"))
async def solitaire_callback_handler(client, cq):
    user_id = cq.from_user.id
    if user_id not in solitaire_games:
        await cq.answer("Start a new game with /solitaire", show_alert=True)
        return
    
    game = solitaire_games[user_id]
    data = cq.data
    
    if data == "solitaire_draw":
        game.draw_from_stock()
    elif data == "solitaire_waste":
        if not game.waste:
            await cq.answer("Waste pile is empty", show_alert=True)
        else:
            game.select_card("waste", -1, -1)
    elif data.startswith("solitaire_foundation_"):
        suit = data.split("_")[2]
        if game.selected_card:
            success, _ = game.move_card("foundation", suit)
            if not success:
                await cq.answer("Invalid move", show_alert=True)
        else:
            game.select_card("foundation", suit, -1)
    elif data.startswith("solitaire_pile_"):
        parts = data.split("_")
        pile_idx = int(parts[2])
        if parts[3] == "top":
            if game.selected_card:
                success, _ = game.move_card("tableau", pile_idx)
                if not success:
                    await cq.answer("Invalid move", show_alert=True)
            else:
                if game.tableau[pile_idx]:
                    game.select_card("tableau", pile_idx, len(game.tableau[pile_idx])-1)
        elif parts[3] == "header":
            if game.tableau[pile_idx]:
                card = game.tableau[pile_idx][-1]
                suit = card[-2:]
                game.select_card("tableau", pile_idx, len(game.tableau[pile_idx])-1)
                success, _ = game.move_card("foundation", suit)
                if not success:
                    await cq.answer("Can't move to foundation", show_alert=True)
    elif data == "solitaire_cancel":
        game.selected_card = None
    elif data == "solitaire_new":
        game = SolitaireGame(user_id)
        solitaire_games[user_id] = game
    elif data == "solitaire_quit":
        del solitaire_games[user_id]
        await cq.message.edit_text("Game ended. Use /solitaire to play again.")
        return
    
    try:
        await cq.message.edit_text(
            game.render_game(),
            reply_markup=game.build_keyboard()
        )
    except Exception as e:
        print(f"Error updating game: {e}")
    
    await cq.answer()

# --- Tic-Tac-Toe Handlers ---
@bot.on_message(filters.command("ttt"))
async def ttt_handler(client, msg: Message):
    user_id = msg.from_user.id
    
    if user_id in ttt_games or any(user_id in game.players for game in online_ttt_games.values()):
        await msg.reply_text("You're already in a Tic-Tac-Toe game! Finish it first.")
        return
    
    game = TicTacToeGame(user_id)
    ttt_games[user_id] = game
    game.message_obj = await msg.reply_text(
        game.render_board(),
        reply_markup=game.build_keyboard()
    )

@bot.on_message(filters.command("onlinettt"))
async def online_ttt_handler(client, msg: Message):
    user_id = msg.from_user.id
    
    # Check if already in a game
    if user_id in ttt_games or any(user_id in game.players for game in online_ttt_games.values()):
        await msg.reply_text("You're already in a Tic-Tac-Toe game! Finish it first.")
        return
    
    if ttt_waiting_queue and ttt_waiting_queue[0] != user_id:
        # Match with waiting player
        p1 = ttt_waiting_queue.pop(0)
        p2 = user_id
        game_id = f"{p1}_{p2}_{random.randint(1000, 9999)}"
        game = TicTacToeGame(p1, p2)
        online_ttt_games[game_id] = game
        
        # Send initial game messages
        await send_ttt_update(game_id, "Game started!")
    else:
        # Add to queue
        ttt_waiting_queue.append(user_id)
        await msg.reply_text(
            "You're in the queue. Waiting for an opponent...\n"
            "Use /cancelqueue to leave.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="ttt_cancel_queue")]
            ])
        )

async def send_ttt_update(game_id: str, message: str = ""):
    game = online_ttt_games.get(game_id)
    if not game:
        return
    
    for player_id in game.players:
        game_text = game.render_board()
        if message:
            game_text = f"{message}\n\n{game_text}"
        
        keyboard = game.build_keyboard()
        
        if player_id in game.messages:
            try:
                await game.messages[player_id].edit_text(game_text, reply_markup=keyboard)
            except:
                game.messages[player_id] = await bot.send_message(player_id, game_text, reply_markup=keyboard)
        else:
            game.messages[player_id] = await bot.send_message(player_id, game_text, reply_markup=keyboard)

@bot.on_message(filters.command("cancelqueue"))
async def cancel_queue_handler(client, msg: Message):
    user_id = msg.from_user.id
    if user_id in ttt_waiting_queue:
        ttt_waiting_queue.remove(user_id)
        await msg.reply_text("You left the queue.")
    else:
        await msg.reply_text("You're not in any queue.")

@bot.on_callback_query(filters.regex("ttt_cancel_queue"))
async def ttt_cancel_queue_callback(client, cq):
    user_id = cq.from_user.id
    if user_id in ttt_waiting_queue:
        ttt_waiting_queue.remove(user_id)
        await cq.message.edit_text("You left the queue.")
    await cq.answer()

@bot.on_callback_query(filters.regex(r"^ttt_"))
async def ttt_callback_handler(client, cq):
    user_id = cq.from_user.id
    
    # Check single player games
    if user_id in ttt_games:
        game = ttt_games[user_id]
        data = cq.data
        
        if data.startswith("ttt_move_"):
            if game.game_over or game.current_player != 0:  # Only player 1 in single player
                await cq.answer("Not your turn!", show_alert=True)
                return
            
            _, _, row, col = data.split("_")
            row, col = int(row), int(col)
            
            if game.make_move(row, col):
                if game.game_over:
                    await cq.message.edit_text(
                        game.render_board(),
                        reply_markup=game.build_keyboard()
                    )
                else:
                    # AI move (simple random)
                    empty_cells = [(r, c) for r in range(3) for c in range(3) if game.board[r][c] == " "]
                    if empty_cells:
                        ai_row, ai_col = random.choice(empty_cells)
                        game.make_move(ai_row, ai_col)
                    
                    await cq.message.edit_text(
                        game.render_board(),
                        reply_markup=game.build_keyboard()
                    )
            else:
                await cq.answer("Invalid move!", show_alert=True)
        
        elif data == "ttt_new":
            game = TicTacToeGame(user_id)
            ttt_games[user_id] = game
            await cq.message.edit_text(
                game.render_board(),
                reply_markup=game.build_keyboard()
            )
        
        elif data == "ttt_quit":
            del ttt_games[user_id]
            await cq.message.edit_text("Game ended. Use /ttt to play again.")
        
        await cq.answer()
        return
    
    # Check multiplayer games
    game_id = next((gid for gid, game in online_ttt_games.items() if user_id in game.players), None)
    if not game_id:
        await cq.answer("Game not found", show_alert=True)
        return
    
    game = online_ttt_games[game_id]
    data = cq.data
    
    if data.startswith("ttt_move_"):
        if game.game_over or game.players[game.current_player] != user_id:
            await cq.answer("Not your turn!", show_alert=True)
            return
        
        _, _, row, col = data.split("_")
        row, col = int(row), int(col)
        
        if game.make_move(row, col):
            await send_ttt_update(game_id)
        else:
            await cq.answer("Invalid move!", show_alert=True)
    
    elif data == "ttt_new":
        if game.game_over:
            p1, p2 = game.players
            new_game_id = f"{p1}_{p2}_{random.randint(1000, 9999)}"
            new_game = TicTacToeGame(p1, p2)
            online_ttt_games[new_game_id] = new_game
            del online_ttt_games[game_id]
            await send_ttt_update(new_game_id, "🔁 New game started!")
        else:
            await cq.answer("Game still in progress", show_alert=True)
    
    elif data == "ttt_quit":
        if game.game_over:
            del online_ttt_games[game_id]
            await cq.message.edit_text("Game ended. Use /onlinettt to play again.")
        else:
            await cq.answer("Finish the game first!", show_alert=True)
    
    await cq.answer()

# --- In-Game Chat ---
@bot.on_message(filters.command("say") & filters.private)
async def say_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /say message")
        return
    
    user_id = msg.from_user.id
    
    # Check Tic-Tac-Toe games
    for game_id, game in online_ttt_games.items():
        if user_id in game.players:
            opponent_id = next(p for p in game.players if p != user_id)
            await bot.send_message(opponent_id, f"💬 Message from opponent:\n{parts[1]}")
            await msg.reply_text("Message sent")
            return
    
    # Check solitaire games (though shouldn't have opponent)
    if user_id in solitaire_games:
        await msg.reply_text("No opponent to message in solitaire")
        return
    
    await msg.reply_text("You're not in any active game")

# --- Greeting Management Commands (Admin Only) ---
@bot.on_message(filters.command("setmorning") & filters.user(MY_USER_ID))
async def set_morning_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setmorning Your new morning message")
        return
    greetings["morning"] = parts[1]
    await msg.reply_text(f"✅ Morning greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("setafternoon") & filters.user(MY_USER_ID))
async def set_afternoon_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setafternoon Your new afternoon message")
        return
    greetings["afternoon"] = parts[1]
    await msg.reply_text(f"✅ Afternoon greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("setnight") & filters.user(MY_USER_ID))
async def set_night_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setnight Your new night message")
        return
    greetings["night"] = parts[1]
    await msg.reply_text(f"✅ Night greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("viewgreetings") & filters.user(MY_USER_ID))
async def view_greetings_handler(client, msg: Message):
    greeting_text = "🌟 Current Greetings:\n\n"
    greeting_text += f"🌅 Morning: {greetings['morning']}\n\n"
    greeting_text += f"🌞 Afternoon: {greetings['afternoon']}\n\n"
    greeting_text += f"🌙 Night: {greetings['night']}\n\n"
    greeting_text += "Use /setmorning, /setafternoon, or /setnight to change them."
    await msg.reply_text(greeting_text)

@bot.on_message(filters.command("resetgreetings") & filters.user(MY_USER_ID))
async def reset_greetings_handler(client, msg: Message):
    greetings["morning"] = "🌞 Good morning bestie have a nice day! 💖"
    greetings["afternoon"] = "🌞 Good Afternoon Kritika Eat well! 💖🎶"
    greetings["night"] = "🌙 Good night Dumb Jigs I Like u the most 💫"
    await msg.reply_text("✅ All greetings have been reset to default!")

@bot.on_message(filters.command("testgreetings") & filters.user(MY_USER_ID))
async def test_greetings_handler(client, msg: Message):
    await msg.reply_text("🧪 Testing all greetings:")
    await asyncio.sleep(1)
    await msg.reply_text(f"Morning: {greetings['morning']}")
    await asyncio.sleep(1)
    await msg.reply_text(f"Afternoon: {greetings['afternoon']}")
    await asyncio.sleep(1)
    await msg.reply_text(f"Night: {greetings['night']}")

# --- Misc Commands ---
@bot.on_message(filters.command("start"))
async def start_handler(client, msg: Message):
    if msg.from_user.id == MY_USER_ID:
        base_text = (
            "Hey Admin! 💌\n\nI'm your special bot.\nCommands:\n"
            "/quote – sweet message 💬\n/photo or /vibe – surprise pic 📸\n/music – vibe 🎶\n"
            "/id – your ID 🔍\n/solitaire – play classic solitaire 🃏\n"
            "/ttt – play Tic-Tac-Toe (vs AI) ❌⭕️\n"
            "/onlinettt – play Tic-Tac-Toe with a friend 🎮\n"
            "/cancelqueue – leave matchmaking queue ❌\n/say – send message to opponent 💬\n\n"
            "🔧 Admin Commands:\n"
            "/viewgreetings – see current greetings 👀\n"
            "/setmorning – change morning message 🌅\n"
            "/setafternoon – change afternoon message 🌞\n"
            "/setnight – change night message 🌙\n"
            "/resetgreetings – reset to defaults 🔄\n"
            "/testgreetings – test all greetings 🧪\n\n"
            "📂 Media Management:\n"
            "/addphoto – enable photo upload mode 📸\n"
            "/addsong – enable song upload mode 🎵\n"
            "/listmedia – view media collection 📋\n"
            "/clearmedia – clear media files 🗑️\n"
            "/done or /cancel – exit upload mode ✅"
        )
    else:
        base_text = (
            "Hey there! 💌\n\nI'm a special bot.\nCommands:\n"
            "/quote – sweet message 💬\n/photo or /vibe – surprise pic 📸\n/music – vibe 🎶\n"
            "/id – your ID 🔍\n/solitaire – play classic solitaire 🃏\n"
            "/ttt – play Tic-Tac-Toe (vs AI) ❌⭕️\n"
            "/onlinettt – play Tic-Tac-Toe with a friend 🎮\n"
            "/cancelqueue – leave matchmaking queue ❌\n/say – send message to opponent 💬"
        )
    
    await msg.reply_text(base_text)

@bot.on_message(filters.command("quote"))
async def quote_handler(client, msg: Message): 
    await msg.reply_text(random.choice(quotes))

@bot.on_message(filters.command(["photo", "vibe"]))
async def photo_handler(client, msg: Message):
    photo_files = get_photo_files()
    if photo_files: 
        await msg.reply_photo(random.choice(photo_files))
    else: 
        await msg.reply_text("No photos available! Ask admin to add some. 📸")

@bot.on_message(filters.command("music"))
async def music_handler(client, msg: Message):
    song_files = get_song_files()
    if song_files: 
        await msg.reply_audio(audio=random.choice(song_files), caption="Vibe 🎧")
    else: 
        await msg.reply_text("No songs available! Ask admin to add some. 🎵")

@bot.on_message(filters.command("id"))
async def id_handler(client, msg: Message): 
    await msg.reply_text(f"Your user ID is: {msg.from_user.id}")

# --- Daily Messages ---
async def send_good_morning(): 
    await bot.send_message(BESTIE_USER_ID, greetings["morning"])

async def send_good_afternoon(): 
    await bot.send_message(BESTIE_USER_ID, greetings["afternoon"])

async def send_good_night(): 
    await bot.send_message(BESTIE_USER_ID, greetings["night"])

scheduler.add_job(send_good_morning, 'cron', hour=6, minute=00)
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
async def root(): 
    return {"message": "Bestie Bot is running!"}

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
