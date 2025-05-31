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

def get_photo_files():
    """Get list of photo files, refreshed each time"""
    return [os.path.join(photo_folder, f) for f in os.listdir(photo_folder) 
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]

def get_song_files():
    """Get list of song files, refreshed each time"""
    return [os.path.join(song_folder, f) for f in os.listdir(song_folder) 
            if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.ogg'))]

# Track upload mode for MY_USER_ID
upload_mode = {"photo": False, "song": False}

# --- Media Upload Handlers ---
@bot.on_message(filters.command("addphoto") & filters.user([MY_USER_ID]))
async def add_photo_mode_handler(client, msg: Message):
    """Enable photo upload mode"""
    upload_mode["photo"] = True
    upload_mode["song"] = False  # Disable song mode
    await msg.reply_text(
        "📸 Photo Upload Mode ON!\n\n"
        "Send me photos to add to the collection.\n"
        "Use /done when finished or /cancel to stop."
    )

@bot.on_message(filters.command("addsong") & filters.user([MY_USER_ID]))
async def add_song_mode_handler(client, msg: Message):
    """Enable song upload mode"""
    upload_mode["song"] = True
    upload_mode["photo"] = False  # Disable photo mode
    await msg.reply_text(
        "🎵 Song Upload Mode ON!\n\n"
        "Send me audio files to add to the collection.\n"
        "Use /done when finished or /cancel to stop."
    )

@bot.on_message(filters.command(["done", "cancel"]) & filters.user([MY_USER_ID]))
async def upload_done_handler(client, msg: Message):
    """Exit upload mode"""
    was_active = upload_mode["photo"] or upload_mode["song"]
    upload_mode["photo"] = False
    upload_mode["song"] = False
    
    if was_active:
        await msg.reply_text("✅ Upload mode disabled!")
    else:
        await msg.reply_text("ℹ️ No upload mode was active.")

@bot.on_message(filters.photo & filters.user([MY_USER_ID]))
async def handle_photo_upload(client, msg: Message):
    """Handle photo uploads when in photo mode"""
    if not upload_mode["photo"]:
        return  # Not in photo upload mode
    
    try:
        # Generate unique filename
        file_id = msg.photo.file_id
        file_extension = "jpg"  # Default for photos
        filename = f"photo_{file_id[:10]}_{random.randint(1000, 9999)}.{file_extension}"
        file_path = os.path.join(photo_folder, filename)
        
        # Download the photo
        await msg.download(file_name=file_path)
        
        await msg.reply_text(f"✅ Photo saved as: {filename}")
        
    except Exception as e:
        await msg.reply_text(f"❌ Error saving photo: {str(e)}")

@bot.on_message(filters.audio & filters.user([MY_USER_ID]))
async def handle_audio_upload(client, msg: Message):
    """Handle audio uploads when in song mode"""
    if not upload_mode["song"]:
        return  # Not in song upload mode
    
    try:
        # Get file info
        audio = msg.audio
        file_id = audio.file_id
        
        # Try to get original filename or create one
        if audio.file_name:
            filename = audio.file_name
        else:
            # Create filename from title/performer or use file_id
            title = audio.title or "Unknown"
            performer = audio.performer or "Unknown"
            extension = "mp3"  # Default
            filename = f"{performer} - {title}_{file_id[:8]}.{extension}"
        
        # Clean filename (remove invalid characters)
        filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
        file_path = os.path.join(song_folder, filename)
        
        # Download the audio
        await msg.download(file_name=file_path)
        
        duration = f"{audio.duration // 60}:{audio.duration % 60:02d}" if audio.duration else "Unknown"
        await msg.reply_text(
            f"✅ Song saved!\n"
            f"📁 Filename: {filename}\n"
            f"⏱️ Duration: {duration}"
        )
        
    except Exception as e:
        await msg.reply_text(f"❌ Error saving song: {str(e)}")

@bot.on_message(filters.document & filters.user([MY_USER_ID]))
async def handle_document_upload(client, msg: Message):
    """Handle document uploads (for audio files sent as documents)"""
    if not upload_mode["song"]:
        return
    
    doc = msg.document
    if not doc.file_name:
        return
    
    # Check if it's an audio file
    audio_extensions = ('.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac')
    if not doc.file_name.lower().endswith(audio_extensions):
        await msg.reply_text("⚠️ Please send only audio files when in song upload mode.")
        return
    
    try:
        filename = doc.file_name
        file_path = os.path.join(song_folder, filename)
        
        # Check if file already exists
        if os.path.exists(file_path):
            base, ext = os.path.splitext(filename)
            filename = f"{base}_{random.randint(1000, 9999)}{ext}"
            file_path = os.path.join(song_folder, filename)
        
        await msg.download(file_name=file_path)
        
        file_size = f"{doc.file_size / (1024*1024):.1f} MB" if doc.file_size else "Unknown size"
        await msg.reply_text(
            f"✅ Audio file saved!\n"
            f"📁 Filename: {filename}\n"
            f"📊 Size: {file_size}"
        )
        
    except Exception as e:
        await msg.reply_text(f"❌ Error saving audio file: {str(e)}")

@bot.on_message(filters.command("listmedia") & filters.user([MY_USER_ID]))
async def list_media_handler(client, msg: Message):
    """List all photos and songs"""
    photos = get_photo_files()
    songs = get_song_files()
    
    response = "📂 **Media Collection:**\n\n"
    response += f"📸 **Photos:** {len(photos)} files\n"
    if photos:
        photo_names = [os.path.basename(p) for p in photos[:5]]  # Show first 5
        response += "• " + "\n• ".join(photo_names)
        if len(photos) > 5:
            response += f"\n• ... and {len(photos) - 5} more"
    response += "\n\n"
    
    response += f"🎵 **Songs:** {len(songs)} files\n"
    if songs:
        song_names = [os.path.basename(s) for s in songs[:5]]  # Show first 5
        response += "• " + "\n• ".join(song_names)
        if len(songs) > 5:
            response += f"\n• ... and {len(songs) - 5} more"
    
    if not photos and not songs:
        response += "Empty collection. Use /addphoto or /addsong to add media!"
    
    await msg.reply_text(response)

@bot.on_message(filters.command("clearmedia") & filters.user([MY_USER_ID]))
async def clear_media_handler(client, msg: Message):
    """Clear all media with confirmation"""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Clear Photos", callback_data="clear_photos"),
            InlineKeyboardButton("🎵 Clear Songs", callback_data="clear_songs")
        ],
        [InlineKeyboardButton("🗑️ Clear All Media", callback_data="clear_all_media")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_clear")]
    ])
    
    photos_count = len(get_photo_files())
    songs_count = len(get_song_files())
    
    await msg.reply_text(
        f"🗑️ **Clear Media Collection**\n\n"
        f"📸 Photos: {photos_count} files\n"
        f"🎵 Songs: {songs_count} files\n\n"
        f"⚠️ **Warning:** This action cannot be undone!",
        reply_markup=keyboard
    )

@bot.on_callback_query(filters.regex("clear_photos") & filters.user([MY_USER_ID]))
async def clear_photos_callback(client, cq):
    """Clear all photos"""
    try:
        photos = get_photo_files()
        for photo in photos:
            os.remove(photo)
        await cq.message.edit_text(f"✅ Cleared {len(photos)} photos!")
    except Exception as e:
        await cq.message.edit_text(f"❌ Error clearing photos: {str(e)}")
    await cq.answer()

@bot.on_callback_query(filters.regex("clear_songs") & filters.user([MY_USER_ID]))
async def clear_songs_callback(client, cq):
    """Clear all songs"""
    try:
        songs = get_song_files()
        for song in songs:
            os.remove(song)
        await cq.message.edit_text(f"✅ Cleared {len(songs)} songs!")
    except Exception as e:
        await cq.message.edit_text(f"❌ Error clearing songs: {str(e)}")
    await cq.answer()

@bot.on_callback_query(filters.regex("clear_all_media") & filters.user([MY_USER_ID]))
async def clear_all_media_callback(client, cq):
    """Clear all media"""
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
    """Cancel clear operation"""
    await cq.message.edit_text("❌ Clear operation cancelled.")
    await cq.answer()

# --- Enhanced Solitaire Game Logic ---
solitaire_games = {}  # user_id: game_data

class SolitaireGame:
    def __init__(self, user_id):
        self.user_id = user_id
        self.deck = self.create_deck()
        self.foundations = {suit: [] for suit in ["♠️", "♥️", "♦️", "♣️"]}
        self.tableau = [[] for _ in range(7)]  # 7 piles
        self.stock = []
        self.waste = []
        self.selected_card = None
        self.selected_pile = None
        self.message = None
        self.message_obj = None
        
        # Deal cards to tableau
        for i in range(7):
            for j in range(i, 7):
                card = self.deck.pop()
                if j == i:  # Last card in each pile is face up
                    self.tableau[j].append(card)
                else:
                    self.tableau[j].append(f"❓{card}")  # Face down
        
        # Remaining cards go to stock
        self.stock = self.deck
    
    def create_deck(self):
        suits = ["♠️", "♥️", "♦️", "♣️"]
        values = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck = [f"{value}{suit}" for suit in suits for value in values]
        random.shuffle(deck)
        return deck
    
    def get_card_value(self, card):
        value = card[:-2]  # Remove suit emoji
        if value == "A":
            return 1
        elif value == "J":
            return 11
        elif value == "Q":
            return 12
        elif value == "K":
            return 13
        else:
            return int(value)
    
    def get_card_color(self, card):
        suit = card[-2:]
        return "red" if suit in ["♥️", "♦️"] else "black"
    
    def is_valid_sequence(self, card1, card2):
        """Check if card2 can be placed on card1 in tableau"""
        val1 = self.get_card_value(card1)
        val2 = self.get_card_value(card2)
        color1 = self.get_card_color(card1)
        color2 = self.get_card_color(card2)
        
        return (val1 == val2 + 1) and (color1 != color2)
    
    def is_valid_foundation_move(self, card, suit):
        """Check if card can be placed on foundation"""
        foundation = self.foundations[suit]
        if not foundation:
            return self.get_card_value(card) == 1  # Only Ace can start
        
        top_card = foundation[-1]
        return (self.get_card_value(card) == (self.get_card_value(top_card) + 1)) and (card[-2:] == top_card[-2:])
    
    def draw_from_stock(self):
        if not self.stock and not self.waste:
            return False
        
        if not self.stock:
            # Recycle waste back to stock (but don't shuffle)
            self.stock = self.waste[::-1]
            self.waste = []
        
        # Draw 3 cards (or remaining if less than 3)
        num_to_draw = min(3, len(self.stock))
        for _ in range(num_to_draw):
            self.waste.append(self.stock.pop())
        
        return True
    
    def select_card(self, pile_type, pile_index, card_index):
        """Select a card for moving"""
        if pile_type == "tableau":
            pile = self.tableau[pile_index]
            if card_index >= len(pile):
                return False
            card = pile[card_index]
            if card.startswith("❓"):
                return False  # Can't select face-down cards
            
            self.selected_card = card
            self.selected_pile = (pile_type, pile_index, card_index)
            return True
        
        elif pile_type == "waste":
            if not self.waste:
                return False
            self.selected_card = self.waste[-1]
            self.selected_pile = (pile_type, -1, -1)
            return True
        
        elif pile_type == "foundation":
            foundation = self.foundations[pile_index]
            if not foundation:
                return False
            self.selected_card = foundation[-1]
            self.selected_pile = (pile_type, pile_index, -1)
            return True
        
        return False
    
    def move_card(self, pile_type, pile_index):
        """Move selected card to destination pile"""
        if not self.selected_card:
            return False, "No card selected"
        
        card = self.selected_card
        
        if pile_type == "tableau":
            # Moving to tableau pile
            dest_pile = self.tableau[pile_index]
            
            if not dest_pile:
                # Empty pile - only Kings can be placed
                if self.get_card_value(card) == 13:
                    self._complete_move(pile_type, pile_index)
                    return True, "King placed on empty pile"
                return False, "Only Kings can be placed on empty piles"
            
            top_card = dest_pile[-1]
            if self.is_valid_sequence(top_card, card):
                self._complete_move(pile_type, pile_index)
                return True, "Card moved successfully"
            return False, "Invalid move - cards must alternate colors and decrease in value"
        
        elif pile_type == "foundation":
            # Moving to foundation
            suit = card[-2:]
            if self.is_valid_foundation_move(card, suit):
                self._complete_move("foundation", suit)
                return True, "Card moved to foundation"
            return False, "Invalid foundation move"
        
        return False, "Invalid destination"
    
    def _complete_move(self, dest_type, dest_index):
        """Complete the move operation"""
        src_type, src_index, card_index = self.selected_pile
        
        if src_type == "tableau":
            # Move all cards from the selected index onward
            cards_to_move = self.tableau[src_index][card_index:]
            self.tableau[src_index] = self.tableau[src_index][:card_index]
            
            # Reveal the next card if it was face down
            if self.tableau[src_index] and self.tableau[src_index][-1].startswith("❓"):
                hidden_card = self.tableau[src_index][-1][1:]
                self.tableau[src_index][-1] = hidden_card
            
            if dest_type == "tableau":
                self.tableau[dest_index].extend(cards_to_move)
            else:  # foundation
                self.foundations[dest_index].extend(cards_to_move)
        
        elif src_type == "waste":
            card = self.waste.pop()
            if dest_type == "tableau":
                self.tableau[dest_index].append(card)
            else:  # foundation
                self.foundations[dest_index].append(card)
        
        elif src_type == "foundation":
            card = self.foundations[src_index].pop()
            if dest_type == "tableau":
                self.tableau[dest_index].append(card)
            else:  # foundation
                self.foundations[dest_index].append(card)
        
        self.selected_card = None
        self.selected_pile = None
    
    def check_win(self):
        """Check if all foundations are complete"""
        for suit, foundation in self.foundations.items():
            if not foundation or self.get_card_value(foundation[-1]) != 13:
                return False
        return True
    
    def render_game(self):
        """Create a text representation of the game state"""
        # Foundations
        foundation_row = " ".join(
            f"{suit}: {foundation[-1] if foundation else '--'}"
            for suit, foundation in self.foundations.items()
        )
        
        # Stock and Waste
        stock_waste = f"Stock: {len(self.stock)} cards | Waste: {self.waste[-1] if self.waste else '--'}"
        
        # Tableau
        tableau_rows = []
        max_pile_height = max(len(pile) for pile in self.tableau)
        
        for i in range(max_pile_height):
            row = []
            for pile in self.tableau:
                if i < len(pile):
                    card = pile[i]
                    if card.startswith("❓"):
                        row.append("🂠")  # Face down card
                    else:
                        row.append(card)
                else:
                    row.append("  ")
            tableau_rows.append(" ".join(row))
        
        # Selected card info
        selected_info = ""
        if self.selected_card:
            selected_info = f"\n\nSelected: {self.selected_card}"
        
        # Game status
        status = ""
        if self.check_win():
            status = "\n\n🎉 YOU WIN! 🎉"
        
        return (
            "🃏 SOLITAIRE 🃏\n\n"
            f"{foundation_row}\n"
            f"{stock_waste}\n\n"
            "Tableau:\n" + "\n".join(tableau_rows) +
            selected_info + status
        )
    
    def build_keyboard(self):
        """Build interactive keyboard for the game"""
        keyboard = []
        
        # Stock/Waste row
        stock_btn = InlineKeyboardButton("🂠 Draw", callback_data="solitaire_draw")
        waste_btn = InlineKeyboardButton(f"Waste: {'🂮' if self.waste else '🂠'}", 
                                       callback_data="solitaire_waste")
        keyboard.append([stock_btn, waste_btn])
        
        # Foundations row
        foundation_btns = []
        for suit in ["♠️", "♥️", "♦️", "♣️"]:
            top_card = self.foundations[suit][-1] if self.foundations[suit] else suit
            foundation_btns.append(
                InlineKeyboardButton(f"F: {top_card}", 
                                   callback_data=f"solitaire_foundation_{suit}")
            )
        keyboard.append(foundation_btns)
        
        # Tableau headers
        header_btns = [
            InlineKeyboardButton(f"Pile {i+1}", callback_data=f"solitaire_pile_{i}_header")
            for i in range(7)
        ]
        keyboard.append(header_btns)
        
        # Tableau cards (show top cards)
        top_card_btns = []
        for i, pile in enumerate(self.tableau):
            if pile:
                card = pile[-1]
                if card.startswith("❓"):
                    btn_text = "🂠"
                else:
                    btn_text = card
                top_card_btns.append(
                    InlineKeyboardButton(btn_text, 
                                       callback_data=f"solitaire_pile_{i}_top")
                )
            else:
                top_card_btns.append(
                    InlineKeyboardButton("🂠", 
                                       callback_data=f"solitaire_pile_{i}_top")
                )
        keyboard.append(top_card_btns)
        
        # Action buttons
        if self.selected_card:
            keyboard.append([
                InlineKeyboardButton("↩️ Cancel", callback_data="solitaire_cancel"),
                InlineKeyboardButton("♻️ New Game", callback_data="solitaire_new")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("♻️ New Game", callback_data="solitaire_new"),
                InlineKeyboardButton("❌ Quit", callback_data="solitaire_quit")
            ])
        
        return InlineKeyboardMarkup(keyboard)

# --- Solitaire Handlers ---
@bot.on_message(filters.command("solitaire"))
async def solitaire_handler(client, msg):
    user_id = msg.from_user.id
    
    # Check if user is already in a game
    if user_id in solitaire_games:
        game = solitaire_games[user_id]
        try:
            await game.message_obj.edit_text(
                game.render_game(),
                reply_markup=game.build_keyboard()
            )
        except:
            # If message editing fails, send a new one
            game.message_obj = await msg.reply_text(
                game.render_game(),
                reply_markup=game.build_keyboard()
            )
        return
    
    # Start new game
    game = SolitaireGame(user_id)
    solitaire_games[user_id] = game
    
    # Send initial game state
    game.message_obj = await msg.reply_text(
        game.render_game(),
        reply_markup=game.build_keyboard()
    )

@bot.on_callback_query(filters.regex(r"^solitaire_"))
async def solitaire_callback_handler(client, cq):
    user_id = cq.from_user.id
    if user_id not in solitaire_games:
        await cq.answer("No active game found. Start a new one with /solitaire", show_alert=True)
        return
    
    game = solitaire_games[user_id]
    data = cq.data
    
    if data == "solitaire_draw":
        game.draw_from_stock()
        await cq.answer("Cards drawn from stock")
    
    elif data == "solitaire_waste":
        if not game.waste:
            await cq.answer("Waste pile is empty", show_alert=True)
        else:
            game.select_card("waste", -1, -1)
            await cq.answer(f"Selected: {game.waste[-1]}")
    
    elif data.startswith("solitaire_foundation_"):
        suit = data.split("_")[2]
        if game.selected_card:
            success, message = game.move_card("foundation", suit)
            await cq.answer(message, show_alert=not success)
        else:
            # Try to select from foundation
            if game.select_card("foundation", suit, -1):
                await cq.answer(f"Selected: {game.selected_card}")
            else:
                await cq.answer("Foundation is empty", show_alert=True)
    
    elif data.startswith("solitaire_pile_"):
        parts = data.split("_")
        pile_idx = int(parts[2])
        card_type = parts[3]
        
        if card_type == "top":
            if game.selected_card:
                # Trying to move selected card to this pile
                success, message = game.move_card("tableau", pile_idx)
                await cq.answer(message, show_alert=not success)
            else:
                # Selecting top card of this pile
                if game.tableau[pile_idx]:
                    if game.select_card("tableau", pile_idx, len(game.tableau[pile_idx])-1):
                        await cq.answer(f"Selected: {game.selected_card}")
                    else:
                        await cq.answer("Can't select face-down cards", show_alert=True)
                else:
                    await cq.answer("Pile is empty", show_alert=True)
        
        elif card_type == "header":
            # Auto-move if possible to foundation
            if game.tableau[pile_idx]:
                card = game.tableau[pile_idx][-1]
                suit = card[-2:]
                if game.is_valid_foundation_move(card, suit):
                    game.select_card("tableau", pile_idx, len(game.tableau[pile_idx])-1)
                    success, message = game.move_card("foundation", suit)
                    await cq.answer(message, show_alert=not success)
                else:
                    await cq.answer("Can't move this card to foundation", show_alert=True)
            else:
                await cq.answer("Pile is empty", show_alert=True)
    
    elif data == "solitaire_cancel":
        game.selected_card = None
        game.selected_pile = None
        await cq.answer("Selection cancelled")
    
    elif data == "solitaire_new":
        # Start new game
        game = SolitaireGame(user_id)
        solitaire_games[user_id] = game
        await cq.answer("New game started!")
    
    elif data == "solitaire_quit":
        del solitaire_games[user_id]
        await cq.message.edit_text("Game ended. Use /solitaire to start a new one.")
        await cq.answer()
        return
    
    # Update the game display
    try:
        await cq.message.edit_text(
            game.render_game(),
            reply_markup=game.build_keyboard()
        )
    except Exception as e:
        print(f"Error updating solitaire game: {e}")
    
    await cq.answer()

# --- Greeting Management Commands ---
@bot.on_message(filters.command("setmorning") & filters.user([BESTIE_USER_ID, MY_USER_ID]))
async def set_morning_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setmorning Your new morning message")
        return
    greetings["morning"] = parts[1]
    await msg.reply_text(f"✅ Morning greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("setafternoon") & filters.user([BESTIE_USER_ID, MY_USER_ID]))
async def set_afternoon_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setafternoon Your new afternoon message")
        return
    greetings["afternoon"] = parts[1]
    await msg.reply_text(f"✅ Afternoon greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("setnight") & filters.user([BESTIE_USER_ID, MY_USER_ID]))
async def set_night_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /setnight Your new night message")
        return
    greetings["night"] = parts[1]
    await msg.reply_text(f"✅ Night greeting updated to:\n{parts[1]}")

@bot.on_message(filters.command("viewgreetings") & filters.user([BESTIE_USER_ID, MY_USER_ID]))
async def view_greetings_handler(client, msg: Message):
    greeting_text = "🌟 Current Greetings:\n\n"
    greeting_text += f"🌅 Morning: {greetings['morning']}\n\n"
    greeting_text += f"🌞 Afternoon: {greetings['afternoon']}\n\n"
    greeting_text += f"🌙 Night: {greetings['night']}\n\n"
    greeting_text += "Use /setmorning, /setafternoon, or /setnight to change them."
    await msg.reply_text(greeting_text)

@bot.on_message(filters.command("resetgreetings") & filters.user([BESTIE_USER_ID, MY_USER_ID]))
async def reset_greetings_handler(client, msg: Message):
    greetings["morning"] = "🌞 Good morning bestie have a nice day! 💖"
    greetings["afternoon"] = "🌞 Good Afternoon Kritika Eat well! 💖🎶"
    greetings["night"] = "🌙 Good night Dumb Jigs I Like u the most 💫"
    await msg.reply_text("✅ All greetings have been reset to default!")

@bot.on_message(filters.command("testgreetings") & filters.user([BESTIE_USER_ID, MY_USER_ID]))
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
async def start_handler(client, msg):
    base_text = (
        "Hey Dumb! 💌\n\nI'm your special bot made with love.\nCommands:\n"
        "/quote – sweet message 💬\n/photo or /vibe – surprise pic 📸\n/music – vibe 🎶\n"
        "/id – your ID 🔍\n/solitaire – play classic solitaire 🃏\n"
    )
    
    # Add greeting management commands only for authorized users
    if msg.from_user.id in [BESTIE_USER_ID, MY_USER_ID]:
        base_text += (
            "\n🔧 **Admin Commands:**\n"
            "/viewgreetings – see current greetings 👀\n"
            "/setmorning – change morning message 🌅\n"
            "/setafternoon – change afternoon message 🌞\n"
            "/setnight – change night message 🌙\n"
            "/resetgreetings – reset to defaults 🔄\n"
            "/testgreetings – test all greetings 🧪\n\n"
            "📂 **Media Management:**\n"
            "/addphoto – enable photo upload mode 📸\n"
            "/addsong – enable song upload mode 🎵\n"
            "/listmedia – view media collection 📋\n"
            "/clearmedia – clear media files 🗑️\n"
            "/done or /cancel – exit upload mode ✅"
        )
    
    await msg.reply_text(base_text)

@bot.on_message(filters.command("quote"))
async def quote_handler(client, msg): 
    await msg.reply_text(random.choice(quotes))

@bot.on_message(filters.command(["photo", "vibe"]))
async def photo_handler(client, msg):
    photo_files = get_photo_files()  # Get fresh list
    if photo_files: 
        await msg.reply_photo(random.choice(photo_files))
    else: 
        await msg.reply_text("No photos available! Ask admin to add some. 📸")

@bot.on_message(filters.command("music"))
async def music_handler(client, msg):
    song_files = get_song_files()  # Get fresh list
    if song_files: 
        await msg.reply_audio(audio=random.choice(song_files), caption="Vibe 🎧")
    else: 
        await msg.reply_text("No songs available! Ask admin to add some. 🎵")

@bot.on_message(filters.command("id"))
async def id_handler(client, msg): 
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
