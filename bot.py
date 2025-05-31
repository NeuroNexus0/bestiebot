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

# --- Single Player Solitaire Game ---
class SolitaireGame:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.deck = self.create_deck()
        self.foundations = {suit: [] for suit in SUITS}
        self.tableau = [[] for _ in range(7)]  # 7 piles
        self.stock = []
        self.waste = []
        self.selected_card = None
        self.selected_pile = None
        self.message_obj = None
        
        # Deal cards to tableau
        for i in range(7):
            for j in range(i, 7):
                card = self.deck.pop()
                if j == i:  # Last card in each pile is face up
                    self.tableau[j].append(card)
                else:
                    self.tableau[j].append(f"❓{card}")  # Face down
        
        self.stock = self.deck
    
    def create_deck(self) -> List[str]:
        deck = [f"{value}{suit}" for suit in SUITS for value in VALUES]
        random.shuffle(deck)
        return deck
    
    def get_card_value(self, card: str) -> int:
        value = card[:-2]
        return {"A": 1, "J": 11, "Q": 12, "K": 13}.get(value, int(value))
    
    def get_card_color(self, card: str) -> str:
        return "red" if card[-2:] in ["♥️", "♦️"] else "black"
    
    def is_valid_sequence(self, card1: str, card2: str) -> bool:
        return (self.get_card_value(card1) == self.get_card_value(card2) + 1 and
                self.get_card_color(card1) != self.get_card_color(card2))
    
    def is_valid_foundation_move(self, card: str, suit: str) -> bool:
        foundation = self.foundations[suit]
        if not foundation:
            return self.get_card_value(card) == 1
        return (self.get_card_value(card) == self.get_card_value(foundation[-1]) + 1 and
                card[-2:] == foundation[-1][-2:])
    
    def draw_from_stock(self) -> bool:
        if not self.stock and not self.waste:
            return False
        
        if not self.stock:
            self.stock = self.waste[::-1]
            self.waste = []
        
        num_to_draw = min(3, len(self.stock))
        for _ in range(num_to_draw):
            self.waste.append(self.stock.pop())
        return True
    
    def select_card(self, pile_type: str, pile_index: int, card_index: int) -> bool:
        if pile_type == "tableau":
            pile = self.tableau[pile_index]
            if card_index >= len(pile) or pile[card_index].startswith("❓"):
                return False
            self.selected_card = pile[card_index]
            self.selected_pile = (pile_type, pile_index, card_index)
            return True
        elif pile_type == "waste" and self.waste:
            self.selected_card = self.waste[-1]
            self.selected_pile = (pile_type, -1, -1)
            return True
        elif pile_type == "foundation" and self.foundations[pile_index]:
            self.selected_card = self.foundations[pile_index][-1]
            self.selected_pile = (pile_type, pile_index, -1)
            return True
        return False
    
    def move_card(self, pile_type: str, pile_index: int) -> Tuple[bool, str]:
        if not self.selected_card:
            return False, "No card selected"
        
        card = self.selected_card
        
        if pile_type == "tableau":
            dest_pile = self.tableau[pile_index]
            if not dest_pile:
                if self.get_card_value(card) != 13:
                    return False, "Only Kings can be placed on empty piles"
            elif not self.is_valid_sequence(dest_pile[-1], card):
                return False, "Invalid sequence"
            self._complete_move(pile_type, pile_index)
            return True, "Card moved"
        
        elif pile_type == "foundation":
            suit = card[-2:]
            if not self.is_valid_foundation_move(card, suit):
                return False, "Invalid foundation move"
            self._complete_move("foundation", suit)
            return True, "Card moved to foundation"
        
        return False, "Invalid move"
    
    def _complete_move(self, dest_type: str, dest_index: int):
        src_type, src_index, card_index = self.selected_pile
        
        if src_type == "tableau":
            cards = self.tableau[src_index][card_index:]
            self.tableau[src_index] = self.tableau[src_index][:card_index]
            
            if self.tableau[src_index] and self.tableau[src_index][-1].startswith("❓"):
                hidden_card = self.tableau[src_index][-1][1:]
                self.tableau[src_index][-1] = hidden_card
            
            if dest_type == "tableau":
                self.tableau[dest_index].extend(cards)
            else:
                self.foundations[dest_index].extend(cards)
        
        elif src_type == "waste":
            card = self.waste.pop()
            if dest_type == "tableau":
                self.tableau[dest_index].append(card)
            else:
                self.foundations[dest_index].append(card)
        
        elif src_type == "foundation":
            card = self.foundations[src_index].pop()
            if dest_type == "tableau":
                self.tableau[dest_index].append(card)
        
        self.selected_card = None
        self.selected_pile = None
    
    def check_win(self) -> bool:
        return all(foundation and self.get_card_value(foundation[-1]) == 13
                   for foundation in self.foundations.values())
    
    def render_game(self) -> str:
        foundation_row = " ".join(
            f"{suit}: {foundation[-1] if foundation else '--'}"
            for suit, foundation in self.foundations.items()
        )
        
        stock_waste = f"Stock: {len(self.stock)} | Waste: {self.waste[-1] if self.waste else '--'}"
        
        tableau_rows = []
        max_height = max(len(pile) for pile in self.tableau)
        for i in range(max_height):
            row = []
            for pile in self.tableau:
                row.append(pile[i] if i < len(pile) else "  ")
            tableau_rows.append(" ".join(row))
        
        selected_info = f"\n\nSelected: {self.selected_card}" if self.selected_card else ""
        status = "\n\n🎉 YOU WIN! 🎉" if self.check_win() else ""
        
        return (
            "🃏 SOLITAIRE 🃏\n\n"
            f"{foundation_row}\n"
            f"{stock_waste}\n\n"
            "Tableau:\n" + "\n".join(tableau_rows) +
            selected_info + status
        )
    
    def build_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = []
        
        # Stock/Waste row
        keyboard.append([
            InlineKeyboardButton("🂠 Draw", callback_data="solitaire_draw"),
            InlineKeyboardButton(f"Waste: {'🂮' if self.waste else '🂠'}", 
                                callback_data="solitaire_waste")
        ])
        
        # Foundations row
        keyboard.append([
            InlineKeyboardButton(f"F: {foundation[-1] if foundation else suit}", 
                                callback_data=f"solitaire_foundation_{suit}")
            for suit, foundation in self.foundations.items()
        ])
        
        # Tableau headers
        keyboard.append([
            InlineKeyboardButton(f"Pile {i+1}", callback_data=f"solitaire_pile_{i}_header")
            for i in range(7)
        ])
        
        # Tableau top cards
        keyboard.append([
            InlineKeyboardButton(
                pile[-1] if pile and not pile[-1].startswith("❓") else "🂠",
                callback_data=f"solitaire_pile_{i}_top"
            ) if pile else InlineKeyboardButton("🂠", callback_data=f"solitaire_pile_{i}_top")
            for i, pile in enumerate(self.tableau)
        ])
        
        # Action buttons
        action_buttons = []
        if self.selected_card:
            action_buttons.append(InlineKeyboardButton("↩️ Cancel", callback_data="solitaire_cancel"))
        action_buttons.extend([
            InlineKeyboardButton("♻️ New Game", callback_data="solitaire_new"),
            InlineKeyboardButton("❌ Quit", callback_data="solitaire_quit")
        ])
        keyboard.append(action_buttons)
        
        return InlineKeyboardMarkup(keyboard)

# --- Game State Management ---
solitaire_games: Dict[int, SolitaireGame] = {}

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
            "/id – your ID 🔍\n/solitaire – play classic solitaire 🃏"
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
