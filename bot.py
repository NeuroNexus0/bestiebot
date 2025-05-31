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

# --- Solitaire Game Logic ---

solitaire_games = {}  # game_id: game_data
solitaire_waiting_queue = []
solitaire_rematch_requests = {}  # For rematch functionality

class SolitaireGame:
    def __init__(self, p1_id, p2_id):
        self.players = {p1_id: {"hand": [], "score": 0}, p2_id: {"hand": [], "score": 0}}
        self.deck = self.create_deck()
        self.discard_pile = []
        self.current_turn = p1_id
        self.game_over = False
        self.winner = None
        self.messages = {}  # player_id: message_object
        self.game_id = f"{p1_id}_{p2_id}_{random.randint(1000, 9999)}"
        
        # Deal 7 cards to each player
        for player_id in self.players:
            self.players[player_id]["hand"] = [self.deck.pop() for _ in range(7)]
        
        # Start discard pile
        self.discard_pile.append(self.deck.pop())
    
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
        elif value in ["J", "Q", "K"]:
            return 10
        else:
            return int(value)
    
    def can_play_card(self, card):
        if not self.discard_pile:
            return True
        
        top_card = self.discard_pile[-1]
        top_suit = top_card[-2:]
        top_value = top_card[:-2]
        card_suit = card[-2:]
        card_value = card[:-2]
        
        return card_suit == top_suit or card_value == top_value
    
    def play_card(self, player_id, card):
        if player_id != self.current_turn:
            return False, "Not your turn!"
        
        if card not in self.players[player_id]["hand"]:
            return False, "You don't have this card!"
        
        if not self.can_play_card(card):
            return False, "Card doesn't match suit or value!"
        
        # Play the card
        self.players[player_id]["hand"].remove(card)
        self.discard_pile.append(card)
        
        # Check if player won
        if len(self.players[player_id]["hand"]) == 0:
            self.game_over = True
            self.winner = player_id
            return True, "You won! 🎉"
        
        # Switch turns
        other_player = [pid for pid in self.players if pid != player_id][0]
        self.current_turn = other_player
        
        return True, "Card played successfully!"
    
    def draw_card(self, player_id):
        if player_id != self.current_turn:
            return False, "Not your turn!"
        
        if not self.deck:
            # Reshuffle discard pile into deck (keep top card)
            if len(self.discard_pile) <= 1:
                return False, "No more cards available!"
            
            top_card = self.discard_pile.pop()
            self.deck = self.discard_pile[:]
            random.shuffle(self.deck)
            self.discard_pile = [top_card]
        
        card = self.deck.pop()
        self.players[player_id]["hand"].append(card)
        
        # Switch turns after drawing
        other_player = [pid for pid in self.players if pid != player_id][0]
        self.current_turn = other_player
        
        return True, f"Drew: {card}"
    
    def get_hand_display(self, player_id):
        hand = self.players[player_id]["hand"]
        if len(hand) > 10:  # Limit display for large hands
            return " ".join(hand[:10]) + f" ... (+{len(hand)-10} more)"
        return " ".join(hand)
    
    def build_game_keyboard(self, player_id):
        hand = self.players[player_id]["hand"]
        keyboard = []
        
        # Show playable cards first
        playable_cards = [card for card in hand if self.can_play_card(card)]
        other_cards = [card for card in hand if not self.can_play_card(card)]
        
        # Create rows of card buttons (3 per row)
        all_cards = playable_cards + other_cards
        for i in range(0, len(all_cards), 3):
            row = []
            for j in range(3):
                if i + j < len(all_cards):
                    card = all_cards[i + j]
                    prefix = "✅" if card in playable_cards else "❌"
                    row.append(InlineKeyboardButton(
                        f"{prefix}{card}", 
                        callback_data=f"solitaire_play_{player_id}_{card}"
                    ))
            keyboard.append(row)
        
        # Add draw card button
        keyboard.append([InlineKeyboardButton("🃏 Draw Card", callback_data=f"solitaire_draw_{player_id}")])
        
        # Add in-game chat button
        keyboard.append([InlineKeyboardButton("💬 Send Message", callback_data=f"solitaire_chat_{player_id}")])
        
        # Add rematch button if game over
        if self.game_over:
            keyboard.append([InlineKeyboardButton("🔁 Rematch", callback_data=f"solitaire_rematch_{player_id}")])
        
        return InlineKeyboardMarkup(keyboard)

# --- Solitaire Handlers ---

@bot.on_message(filters.command("solitaire"))
async def solitaire_handler(client, msg):
    user_id = msg.from_user.id
    
    # Check if user is already in queue
    if user_id in solitaire_waiting_queue:
        await msg.reply_text("❌ You're already in the solitaire queue! Use /cancelsolitaire to leave.")
        return
    
    # Check if user is already in a game
    for game_id, game in solitaire_games.items():
        if user_id in game.players:
            await msg.reply_text("❌ You're already in a solitaire game! Finish it first.")
            return
    
    if solitaire_waiting_queue and solitaire_waiting_queue[0] != user_id:
        # Match with waiting player
        p1_id = solitaire_waiting_queue.pop(0)
        p2_id = user_id
        
        game = SolitaireGame(p1_id, p2_id)
        solitaire_games[game.game_id] = game
        
        # Send game messages to both players
        await send_solitaire_update(game.game_id, "🃏 Solitaire game started!")
        
    else:
        # Add to queue
        solitaire_waiting_queue.append(user_id)
        cancel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel Queue", callback_data="cancel_solitaire_queue")]
        ])
        await msg.reply_text(
            "🃏 You're in the solitaire queue. Waiting for an opponent...\n"
            "Use /cancelsolitaire or the button below to leave the queue.", 
            reply_markup=cancel_markup
        )

@bot.on_message(filters.command("cancelsolitaire"))
async def cancel_solitaire_handler(client, msg):
    user_id = msg.from_user.id
    if user_id in solitaire_waiting_queue:
        solitaire_waiting_queue.remove(user_id)
        await msg.reply_text("✅ You've been removed from the solitaire queue.")
    else:
        await msg.reply_text("❌ You're not in the solitaire queue.")

@bot.on_callback_query(filters.regex("cancel_solitaire_queue"))
async def cancel_solitaire_queue_callback(client, cq):
    user_id = cq.from_user.id
    if user_id in solitaire_waiting_queue:
        solitaire_waiting_queue.remove(user_id)
        await cq.message.edit_text("✅ You've been removed from the solitaire queue.")
    else:
        await cq.answer("You're not in the queue.", show_alert=True)
    await cq.answer()

async def send_solitaire_update(game_id, message=""):
    game = solitaire_games.get(game_id)
    if not game:
        return
    
    for player_id in game.players:
        try:
            other_player = [pid for pid in game.players if pid != player_id][0]
            
            game_text = f"🃏 **Solitaire Game**\n\n"
            if message:
                game_text += f"{message}\n\n"
            
            game_text += f"**Top Card:** {game.discard_pile[-1] if game.discard_pile else 'None'}\n"
            game_text += f"**Cards Left:** You: {len(game.players[player_id]['hand'])}, Opponent: {len(game.players[other_player]['hand'])}\n"
            game_text += f"**Turn:** {'Your turn' if game.current_turn == player_id else 'Opponent turn'}\n\n"
            
            if game.game_over:
                if game.winner == player_id:
                    game_text += "🎉 **You Won!** 🎉"
                else:
                    game_text += "😔 **You Lost!** Better luck next time."
            
            game_text += f"\n\n**Your Hand:** {game.get_hand_display(player_id)}\n"
            game_text += "✅ = Can play, ❌ = Can't play"
            
            keyboard = game.build_game_keyboard(player_id)
            
            if player_id in game.messages:
                await game.messages[player_id].edit_text(game_text, reply_markup=keyboard)
            else:
                msg = await bot.send_message(player_id, game_text, reply_markup=keyboard)
                game.messages[player_id] = msg
                
        except Exception as e:
            print(f"Error sending solitaire update to {player_id}: {e}")

@bot.on_callback_query(filters.regex(r"solitaire_play_(\d+)_(.+)"))
async def solitaire_play_callback(client, cq):
    player_id = int(cq.data.split("_")[2])
    card = "_".join(cq.data.split("_")[3:])  # Handle multi-part card names
    
    if cq.from_user.id != player_id:
        await cq.answer("This is not your game!", show_alert=True)
        return
    
    # Find the game
    game_id = None
    for gid, game in solitaire_games.items():
        if player_id in game.players:
            game_id = gid
            break
    
    if not game_id:
        await cq.answer("Game not found!", show_alert=True)
        return
    
    game = solitaire_games[game_id]
    success, message = game.play_card(player_id, card)
    
    if success:
        await send_solitaire_update(game_id, f"Player played {card}")
        if game.game_over:
            # Add rematch option
            await asyncio.sleep(2)
            await send_solitaire_update(game_id)
    else:
        await cq.answer(message, show_alert=True)
    
    await cq.answer()

@bot.on_callback_query(filters.regex(r"solitaire_draw_(\d+)"))
async def solitaire_draw_callback(client, cq):
    player_id = int(cq.data.split("_")[2])
    
    if cq.from_user.id != player_id:
        await cq.answer("This is not your game!", show_alert=True)
        return
    
    # Find the game
    game_id = None
    for gid, game in solitaire_games.items():
        if player_id in game.players:
            game_id = gid
            break
    
    if not game_id:
        await cq.answer("Game not found!", show_alert=True)
        return
    
    game = solitaire_games[game_id]
    success, message = game.draw_card(player_id)
    
    if success:
        await send_solitaire_update(game_id, message)
    else:
        await cq.answer(message, show_alert=True)
    
    await cq.answer()

@bot.on_callback_query(filters.regex(r"solitaire_chat_(\d+)"))
async def solitaire_chat_callback(client, cq):
    player_id = int(cq.data.split("_")[2])
    
    if cq.from_user.id != player_id:
        await cq.answer("This is not your game!", show_alert=True)
        return
    
    await cq.answer("Use /say followed by your message to chat with your opponent!", show_alert=True)
    await cq.answer()

@bot.on_callback_query(filters.regex(r"solitaire_rematch_(\d+)"))
async def solitaire_rematch_callback(client, cq):
    player_id = int(cq.data.split("_")[2])
    game_id = None
    
    # Find the game
    for gid, game in solitaire_games.items():
        if player_id in game.players:
            game_id = gid
            break
    
    if not game_id:
        await cq.answer("Game not found!", show_alert=True)
        return
    
    game = solitaire_games[game_id]
    if not game.game_over:
        await cq.answer("Game is still in progress!", show_alert=True)
        return
    
    other_player = [pid for pid in game.players if pid != player_id][0]
    key = tuple(sorted([player_id, other_player]))
    
    solitaire_rematch_requests.setdefault(key, set()).add(player_id)
    
    if len(solitaire_rematch_requests[key]) == 2:
        del solitaire_rematch_requests[key]
        # Start new game with same players
        new_game = SolitaireGame(player_id, other_player)
        solitaire_games[new_game.game_id] = new_game
        await send_solitaire_update(new_game.game_id, "🔁 Rematch started!")
    else:
        await cq.answer("Rematch request sent. Waiting for opponent...", show_alert=True)
    
    await cq.answer()

@bot.on_message(filters.command("say") & filters.private)
async def say_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /say message")
        return
    uid = msg.from_user.id
    
    # Check if in solitaire game
    for game_id, game in solitaire_games.items():
        if uid in game.players:
            peer = [pid for pid in game.players if pid != uid][0]
            await bot.send_message(peer, f"💬 Message from your opponent:\n{parts[1]}")
            await msg.reply_text("Message sent to opponent.")
            return
    
    await msg.reply_text("No active game found.")

# --- Greeting Management Commands (Only for BESTIE_USER_ID) ---

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
        "/id – your ID 🔍\n/solitaire – play card game 🃏\n"
        "/cancelsolitaire – leave queue ❌\n/say – message opponent 💬"
    )
    
    # Add greeting management commands only for authorized users
    if msg.from_user.id in [BESTIE_USER_ID, MY_USER_ID]:
        base_text += (
            "\n\n🔧 **Admin Commands:**\n"
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
