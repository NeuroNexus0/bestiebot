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
from typing import Dict, List, Tuple, Optional

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
    return [os.path.join(photo_folder, f) for f in os.listdir(photo_folder) 
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]

def get_song_files():
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
        return [f"{value}{suit}" for suit in SUITS for value in VALUES]
    
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

# --- Multiplayer Card Game ---
class MultiplayerCardGame:
    def __init__(self, player1_id: int, player2_id: int):
        self.players = {
            player1_id: {"hand": [], "score": 0},
            player2_id: {"hand": [], "score": 0}
        }
        self.deck = self.create_deck()
        self.discard_pile = []
        self.current_turn = player1_id
        self.game_over = False
        self.winner = None
        self.messages = {}  # player_id: message_object
    
    def create_deck(self) -> List[str]:
        return [f"{value}{suit}" for suit in SUITS for value in VALUES] * 2  # Double deck
    
    def get_card_value(self, card: str) -> int:
        value = card[:-2]
        return {"A": 1, "J": 11, "Q": 12, "K": 13}.get(value, int(value))
    
    def can_play_card(self, card: str) -> bool:
        if not self.discard_pile:
            return True
        top_card = self.discard_pile[-1]
        return card[-2:] == top_card[-2:] or card[:-2] == top_card[:-2]
    
    def deal_initial_hands(self):
        for player in self.players.values():
            player["hand"] = [self.deck.pop() for _ in range(7)]
        self.discard_pile.append(self.deck.pop())
    
    def play_card(self, player_id: int, card: str) -> Tuple[bool, str]:
        if player_id != self.current_turn:
            return False, "Not your turn!"
        if card not in self.players[player_id]["hand"]:
            return False, "You don't have this card!"
        if not self.can_play_card(card):
            return False, "Card doesn't match suit or value!"
        
        self.players[player_id]["hand"].remove(card)
        self.discard_pile.append(card)
        
        if not self.players[player_id]["hand"]:
            self.game_over = True
            self.winner = player_id
            return True, "You won! 🎉"
        
        self.current_turn = next(p for p in self.players if p != player_id)
        return True, "Card played successfully!"
    
    def draw_card(self, player_id: int) -> Tuple[bool, str]:
        if player_id != self.current_turn:
            return False, "Not your turn!"
        if not self.deck:
            return False, "No cards left to draw!"
        
        card = self.deck.pop()
        self.players[player_id]["hand"].append(card)
        self.current_turn = next(p for p in self.players if p != player_id)
        return True, f"You drew: {card}"
    
    def get_hand_display(self, player_id: int) -> str:
        hand = self.players[player_id]["hand"]
        return " ".join(hand[:10]) + (f" (+{len(hand)-10} more)" if len(hand) > 10 else "")
    
    def build_game_keyboard(self, player_id: int) -> InlineKeyboardMarkup:
        hand = self.players[player_id]["hand"]
        playable = [card for card in hand if self.can_play_card(card)]
        unplayable = [card for card in hand if not self.can_play_card(card)]
        
        keyboard = []
        for i in range(0, len(hand), 3):
            row = []
            for j in range(3):
                if i + j < len(playable):
                    card = playable[i + j]
                    row.append(InlineKeyboardButton(f"✅{card}", callback_data=f"mp_play_{player_id}_{card}"))
                elif i + j - len(playable) < len(unplayable):
                    card = unplayable[i + j - len(playable)]
                    row.append(InlineKeyboardButton(f"❌{card}", callback_data=f"mp_play_{player_id}_{card}"))
            if row:
                keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🃏 Draw Card", callback_data=f"mp_draw_{player_id}")])
        keyboard.append([InlineKeyboardButton("💬 Chat", callback_data=f"mp_chat_{player_id}")])
        
        if self.game_over:
            keyboard.append([InlineKeyboardButton("🔁 Rematch", callback_data=f"mp_rematch_{player_id}")])
        
        return InlineKeyboardMarkup(keyboard)

# --- Game State Management ---
solitaire_games: Dict[int, SolitaireGame] = {}
mp_games: Dict[str, MultiplayerCardGame] = {}  # game_id: game
mp_waiting_queue: List[int] = []
mp_rematch_requests: Dict[Tuple[int, int], set] = {}

# --- Media Handlers (same as before) ---
# [Previous media upload/download/list/clear handlers remain unchanged]
# [Previous greeting management commands remain unchanged]

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

# --- Multiplayer Game Handlers ---
@bot.on_message(filters.command("playcards"))
async def multiplayer_handler(client, msg: Message):
    user_id = msg.from_user.id
    
    # Check if already in a game
    for game_id, game in mp_games.items():
        if user_id in game.players:
            await msg.reply_text("You're already in a game! Finish it first.")
            return
    
    if mp_waiting_queue and mp_waiting_queue[0] != user_id:
        # Match with waiting player
        p1 = mp_waiting_queue.pop(0)
        p2 = user_id
        game_id = f"{p1}_{p2}_{random.randint(1000, 9999)}"
        game = MultiplayerCardGame(p1, p2)
        game.deal_initial_hands()
        mp_games[game_id] = game
        
        # Send initial game messages
        await send_mp_update(game_id, "Game started!")
    else:
        # Add to queue
        mp_waiting_queue.append(user_id)
        await msg.reply_text(
            "You're in the queue. Waiting for an opponent...\n"
            "Use /cancelqueue to leave.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="mp_cancel_queue")]
            ])
        )

async def send_mp_update(game_id: str, message: str = ""):
    game = mp_games.get(game_id)
    if not game:
        return
    
    for player_id in game.players:
        opponent_id = next(p for p in game.players if p != player_id)
        
        game_text = (
            f"🎴 Multiplayer Card Game\n\n"
            f"Top card: {game.discard_pile[-1] if game.discard_pile else 'None'}\n"
            f"Cards left: You: {len(game.players[player_id]['hand'])}, Opponent: {len(game.players[opponent_id]['hand'])}\n"
            f"Turn: {'Your turn' if game.current_turn == player_id else 'Opponent turn'}\n\n"
        )
        
        if message:
            game_text += f"{message}\n\n"
        
        if game.game_over:
            if game.winner == player_id:
                game_text += "🎉 You won! 🎉"
            else:
                game_text += "😔 You lost!"
        else:
            game_text += f"Your hand: {game.get_hand_display(player_id)}\n"
            game_text += "✅ = Playable, ❌ = Can't play"
        
        keyboard = game.build_game_keyboard(player_id)
        
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
    if user_id in mp_waiting_queue:
        mp_waiting_queue.remove(user_id)
        await msg.reply_text("You left the queue.")
    else:
        await msg.reply_text("You're not in any queue.")

@bot.on_callback_query(filters.regex("mp_cancel_queue"))
async def mp_cancel_queue_callback(client, cq):
    user_id = cq.from_user.id
    if user_id in mp_waiting_queue:
        mp_waiting_queue.remove(user_id)
        await cq.message.edit_text("You left the queue.")
    await cq.answer()

@bot.on_callback_query(filters.regex(r"mp_play_(\d+)_(.+)"))
async def mp_play_callback(client, cq):
    player_id = int(cq.data.split("_")[2])
    card = "_".join(cq.data.split("_")[3:])
    
    if cq.from_user.id != player_id:
        await cq.answer("Not your game!", show_alert=True)
        return
    
    game_id = next((gid for gid, game in mp_games.items() if player_id in game.players), None)
    if not game_id:
        await cq.answer("Game not found", show_alert=True)
        return
    
    game = mp_games[game_id]
    success, message = game.play_card(player_id, card)
    
    if not success:
        await cq.answer(message, show_alert=True)
    else:
        await send_mp_update(game_id, f"Player played {card}")
        if game.game_over:
            await asyncio.sleep(2)
            await send_mp_update(game_id)
    
    await cq.answer()

@bot.on_callback_query(filters.regex(r"mp_draw_(\d+)"))
async def mp_draw_callback(client, cq):
    player_id = int(cq.data.split("_")[2])
    
    if cq.from_user.id != player_id:
        await cq.answer("Not your game!", show_alert=True)
        return
    
    game_id = next((gid for gid, game in mp_games.items() if player_id in game.players), None)
    if not game_id:
        await cq.answer("Game not found", show_alert=True)
        return
    
    game = mp_games[game_id]
    success, message = game.draw_card(player_id)
    
    if success:
        await send_mp_update(game_id, message)
    else:
        await cq.answer(message, show_alert=True)
    
    await cq.answer()

@bot.on_callback_query(filters.regex(r"mp_rematch_(\d+)"))
async def mp_rematch_callback(client, cq):
    player_id = int(cq.data.split("_")[2])
    
    game_id = next((gid for gid, game in mp_games.items() if player_id in game.players), None)
    if not game_id:
        await cq.answer("Game not found", show_alert=True)
        return
    
    game = mp_games[game_id]
    if not game.game_over:
        await cq.answer("Game still in progress", show_alert=True)
        return
    
    opponent_id = next(p for p in game.players if p != player_id)
    key = tuple(sorted([player_id, opponent_id]))
    
    mp_rematch_requests.setdefault(key, set()).add(player_id)
    
    if len(mp_rematch_requests[key]) == 2:
        del mp_rematch_requests[key]
        new_game_id = f"{player_id}_{opponent_id}_{random.randint(1000, 9999)}"
        new_game = MultiplayerCardGame(player_id, opponent_id)
        new_game.deal_initial_hands()
        mp_games[new_game_id] = new_game
        await send_mp_update(new_game_id, "🔁 Rematch started!")
    else:
        await cq.answer("Rematch requested", show_alert=True)
    
    await cq.answer()

# --- In-Game Chat ---
@bot.on_message(filters.command("say") & filters.private)
async def say_handler(client, msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply_text("Usage: /say message")
        return
    
    user_id = msg.from_user.id
    
    # Check multiplayer games
    for game_id, game in mp_games.items():
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

# --- Other Handlers (Start, Quotes, Media, etc.) ---
# [All previous handlers for start, quotes, photos, music, id remain unchanged]
# [All previous greeting management commands remain unchanged]
# [All previous media upload/download/list/clear handlers remain unchanged]

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
