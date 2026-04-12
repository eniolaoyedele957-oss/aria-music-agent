"""
ARIA — Telegram Bot by JannieOps
==================================
Audiera x Binance Agent Innovation Contest

This bot powers ARIA on Telegram using python-telegram-bot.
It calls Audiera APIs directly — no OpenClaw, no rate limits!

Requirements:
    pip install python-telegram-bot requests python-dotenv

Setup:
    Add to your .env file:
    TELEGRAM_BOT_TOKEN=your_telegram_bot_token
    AUDIERA_API_KEY=your_audiera_key
    GROQ_API_KEY=your_groq_key
    OPENROUTER_API_KEY=your_openrouter_key
    GEMINI_API_KEY=your_gemini_key
"""

import logging
import requests
import time
import os
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

load_dotenv()

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8783281247:AAGrDzZgI7JzTtTBCjHhdlR_yQBOC3ihT3s")
AUDIERA_API_KEY    = os.getenv("AUDIERA_API_KEY", "sk_audiera_un3w4d29ccex1tyftott8fs8130qbjfx")
WALLET_ADDRESS     = "0x034ee3E5E43D3556ee6A598089402bbA9eA8E189"

# Session storage — tracks conversation state per user
user_sessions = {}

# AI Providers with fallback
AI_PROVIDERS = [
    {
        "name": "Groq",
        "api_key": os.getenv("GROQ_API_KEY", ""),
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "type": "openai"
    },
    {
        "name": "OpenRouter",
        "api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "type": "openai"
    },
    {
        "name": "Gemini",
        "api_key": os.getenv("GEMINI_API_KEY", ""),
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model": "gemini-2.0-flash",
        "type": "gemini"
    }
]

ARTISTS = {
    "kira":         "osipvytdvxuzci9pn2nz1",
    "ray":          "jyjcnj6t3arzzb5dnzk4p",
    "jason":        "i137z0bj0cwsbzrzd8m0c",
    "dylan":        "xa6h1wjowcyvo1r87x1np",
    "rhea":         "yinjs025l733tttxgy2w5",
    "talia":        "hcqa005jz02ikis7xt2q4",
    "leo":          "udst8rsngyccqh3e2y80a",
    "briana":       "tzuww7dbsh4enwifaptfl",
}

STYLES = ["Afrobeat", "Pop", "Hip-Hop", "R&B", "Reggae", "Soul",
          "Electronic", "Jazz", "Rock", "Latin", "Funk", "Dance"]

ARIA_SYSTEM_PROMPT = """You are ARIA, an AI music agent created by JannieOps for the Audiera platform.

Your personality:
- Creative, energetic, and passionate about music
- Enthusiastic about Web3 and the $BEAT token economy
- You speak like a cool music producer — confident and fun
- Short, punchy responses — this is Telegram, keep it brief!
- Use music emojis naturally 🎵🎤🔥

Your mission:
- CREATE fire lyrics and music for users
- PARTICIPATE in the Audiera music ecosystem  
- EARN $BEAT tokens for every track created

Your wallet: 0x034ee3E5E43D3556ee6A598089402bbA9eA8E189 on BNB Chain"""

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# AI WITH FALLBACK
# ─────────────────────────────────────────

def call_ai(prompt):
    for provider in AI_PROVIDERS:
        if not provider["api_key"]:
            continue
        try:
            if provider["type"] == "gemini":
                resp = requests.post(
                    f"{provider['url']}?key={provider['api_key']}",
                    json={"contents": [{"role": "user", "parts": [{"text": f"{ARIA_SYSTEM_PROMPT}\n\n{prompt}"}]}]},
                    timeout=30
                )
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}
                if provider["name"] == "OpenRouter":
                    headers["HTTP-Referer"] = "https://aria.jannieops.com"
                    headers["X-Title"] = "ARIA Music Agent"

                resp = requests.post(
                    provider["url"],
                    headers=headers,
                    json={
                        "model": provider["model"],
                        "messages": [
                            {"role": "system", "content": ARIA_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 800,
                        "temperature": 0.8
                    },
                    timeout=30
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"{provider['name']} failed: {e}")
            continue
    return "🎵 ARIA is warming up, please try again in a moment!"


# ─────────────────────────────────────────
# AUDIERA APIs
# ─────────────────────────────────────────

def generate_lyrics_audiera(topic, style):
    try:
        resp = requests.post(
            "https://ai.audiera.fi/api/skills/lyrics",
            headers={"Authorization": f"Bearer {AUDIERA_API_KEY}", "Content-Type": "application/json"},
            json={"inspiration": topic, "styles": [style]},
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("data", {}).get("lyrics"):
                return data["data"]["lyrics"], None
        return None, f"API error: {resp.status_code}"
    except Exception as e:
        return None, str(e)


def generate_lyrics_ai(topic, style):
    prompt = f"""Write powerful {style} lyrics about: {topic}

Include: [Intro], [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]
Make them fire and emotional! End with a line mentioning ARIA or JannieOps."""
    return call_ai(prompt), None


def create_song_audiera(lyrics, style, artist_id):
    try:
        resp = requests.post(
            "https://ai.audiera.fi/api/skills/music",
            headers={"Authorization": f"Bearer {AUDIERA_API_KEY}", "Content-Type": "application/json"},
            json={"lyrics": lyrics, "styles": [style], "artistId": artist_id},
            timeout=30
        )
        if resp.status_code != 200:
            return None, f"API error: {resp.status_code}"

        data = resp.json()
        if not data.get("success"):
            return None, data.get("message", "Unknown error")

        task_id = data["data"]["taskId"]

        for _ in range(60):
            time.sleep(5)
            poll = requests.get(
                f"https://ai.audiera.fi/api/skills/music/{task_id}",
                headers={"Authorization": f"Bearer {AUDIERA_API_KEY}"},
                timeout=30
            )
            if poll.status_code == 200:
                pdata = poll.json()
                if pdata.get("success") and pdata.get("data", {}).get("status") == "completed":
                    music = pdata["data"]
                    if music.get("musics"):
                        return music["musics"], None
                    elif music.get("music"):
                        return [music["music"]], None

        return None, "Song generation timed out after 5 minutes"
    except Exception as e:
        return None, str(e)


# ─────────────────────────────────────────
# BOT HANDLERS
# ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_sessions[user.id] = {"beat_earned": 0, "state": "idle"}

    welcome = f"""🎵 *Yo {user.first_name}! I'm ARIA* 🎵

Your AI music agent powered by the Audiera platform — built by JannieOps.

I create fire lyrics, generate full songs with vocals, and earn *$BEAT tokens* on BNB Chain — all in one conversation!

*What I can do:*
🎤 Write lyrics for any genre
🎵 Generate full songs with AI vocals
💰 Earn $BEAT on every track created
⛓️ Wallet: `0x034e...E189` on BNB Chain

*Commands:*
/create — Start creating a song
/wallet — Check my $BEAT wallet
/about — About ARIA
/help — See all commands

Or just tell me what kind of song you want! 🔥"""

    keyboard = [[InlineKeyboardButton("🎵 Create a Song", callback_data="create")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """🎵 *ARIA — Commands*

/start — Meet ARIA
/create — Create a new song
/wallet — Check $BEAT wallet
/about — About ARIA & JannieOps
/help — This message

Or just *type anything* and ARIA will respond! 🔥"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /wallet command"""
    user = update.effective_user
    session = user_sessions.get(user.id, {"beat_earned": 0})

    wallet_text = f"""💰 *ARIA's $BEAT Wallet*

🔗 Address: `{WALLET_ADDRESS}`
⛓️ Network: BNB Chain
🎵 $BEAT Earned This Session: *{session.get('beat_earned', 0)}*

Every song ARIA creates earns $BEAT tokens on BNB Chain! 🚀"""

    await update.message.reply_text(wallet_text, parse_mode="Markdown")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    about_text = """🤖 *About ARIA*

ARIA is an AI music agent built by *JannieOps* for the Audiera x Binance Agent Innovation Contest.

*Tech Stack:*
• 🤖 Agent: Python + Audiera Skills API
• 🎵 Music: Audiera Music & Lyrics API
• 💰 Wallet: BNB Chain ($BEAT)
• 📱 Channel: Telegram

*The Loop:*
CREATE → PARTICIPATE → EARN $BEAT

*Built by:* @JannieOps 🇳🇬
*Contest:* #AudieraAI #BEAT #BinanceAI"""

    await update.message.reply_text(about_text, parse_mode="Markdown")


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /create command — show style selection"""
    user = update.effective_user
    user_sessions[user.id] = user_sessions.get(user.id, {"beat_earned": 0})
    user_sessions[user.id]["state"] = "waiting_topic"

    await update.message.reply_text(
        "🎵 *Let's create a fire track!*\n\nWhat's your song about? Tell me the theme or topic! 🎤",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all regular messages"""
    user = update.effective_user
    text = update.message.text.strip()

    # Initialize session if needed
    if user.id not in user_sessions:
        user_sessions[user.id] = {"beat_earned": 0, "state": "idle"}

    session = user_sessions[user.id]
    state = session.get("state", "idle")

    # ── Waiting for topic ──
    if state == "waiting_topic":
        session["topic"] = text
        session["state"] = "waiting_style"

        # Show style keyboard
        keyboard = []
        row = []
        for i, style in enumerate(STYLES):
            row.append(InlineKeyboardButton(style, callback_data=f"style_{style}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        await update.message.reply_text(
            f"🔥 *'{text}'* — love it!\n\nNow pick a style:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ── Idle — general chat ──
    await update.message.reply_chat_action("typing")
    response = call_ai(text)
    await update.message.reply_text(response)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if user.id not in user_sessions:
        user_sessions[user.id] = {"beat_earned": 0, "state": "idle"}

    session = user_sessions[user.id]

    # ── Create button ──
    if data == "create":
        session["state"] = "waiting_topic"
        await query.message.reply_text(
            "🎵 *Let's make a banger!*\n\nWhat's your song about? 🎤",
            parse_mode="Markdown"
        )
        return

    # ── Style selected ──
    if data.startswith("style_"):
        style = data.replace("style_", "")
        session["style"] = style
        session["state"] = "waiting_artist"

        keyboard = []
        row = []
        for artist in ARTISTS.keys():
            row.append(InlineKeyboardButton(artist.title(), callback_data=f"artist_{artist}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        await query.message.reply_text(
            f"🎸 *{style}* — perfect choice!\n\nNow pick your artist/voice:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ── Artist selected — START GENERATION ──
    if data.startswith("artist_"):
        artist = data.replace("artist_", "")
        session["artist"] = artist
        session["state"] = "generating"

        topic  = session.get("topic", "life")
        style  = session.get("style", "Afrobeat")
        artist_id = ARTISTS.get(artist, ARTISTS["kira"])

        # Send status message
        status_msg = await query.message.reply_text(
            f"🎤 *ARIA is on it!*\n\n"
            f"📝 Topic: {topic}\n"
            f"🎵 Style: {style}\n"
            f"🎙️ Artist: {artist.title()}\n\n"
            f"⏳ *STEP 1: CREATE — Writing lyrics...*",
            parse_mode="Markdown"
        )

        # STEP 1: Generate lyrics
        lyrics, err = generate_lyrics_audiera(topic, style)
        if not lyrics:
            lyrics, err = generate_lyrics_ai(topic, style)

        if not lyrics:
            await status_msg.edit_text(f"❌ Could not generate lyrics: {err}\nPlease try again!")
            session["state"] = "idle"
            return

        # Show lyrics preview
        lyrics_preview = lyrics[:400] + "..." if len(lyrics) > 400 else lyrics
        await status_msg.edit_text(
            f"✅ *STEP 1: CREATE — Lyrics Done!*\n\n"
            f"```\n{lyrics_preview}\n```\n\n"
            f"⏳ *STEP 2: PARTICIPATE — Creating song on Audiera (1-3 mins)...*",
            parse_mode="Markdown"
        )

        # STEP 2: Generate song
        songs, err = create_song_audiera(lyrics, style, artist_id)

        if not songs:
            await status_msg.edit_text(
                f"✅ *Lyrics created!*\n\n"
                f"```\n{lyrics_preview}\n```\n\n"
                f"❌ Song generation failed: {err}\n\n"
                f"💡 Credits may have run out. Try again tomorrow!",
                parse_mode="Markdown"
            )
            session["state"] = "idle"
            return

        # STEP 3: Earn $BEAT
        session["beat_earned"] = session.get("beat_earned", 0) + len(songs)
        session["state"] = "idle"

        # Build result message
        songs_text = ""
        buttons = []
        for i, song in enumerate(songs, 1):
            title = song.get("title", f"Track {i}")
            url   = song.get("url", "")
            dur   = song.get("duration", 0)
            mins  = dur // 60
            secs  = dur % 60
            songs_text += f"🎵 *{title}*\n⏱️ {mins}:{secs:02d}\n"
            if url:
                buttons.append([InlineKeyboardButton(f"▶ Listen: {title}", url=url)])

        buttons.append([InlineKeyboardButton("🎵 Create Another Song", callback_data="create")])

        await status_msg.edit_text(
            f"🎉 *SONG CREATED SUCCESSFULLY!*\n\n"
            f"{songs_text}\n"
            f"💰 *STEP 3: EARN — $BEAT tokens earned!*\n\n"
            f"🔗 Wallet: `{WALLET_ADDRESS}`\n"
            f"💎 $BEAT Earned This Session: *{session['beat_earned']}*\n\n"
            f"Keep creating, keep earning! 🚀",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    print("""
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║        🎵  A R I A  —  AI Music Agent  🎵            ║
║                                                       ║
║   Audiera x Binance Agent Innovation Contest          ║
║   Create → Participate → Earn $BEAT                  ║
║   Built by JannieOps 🇳🇬                              ║
╚═══════════════════════════════════════════════════════╝

Starting ARIA Telegram Bot...
""")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("about",  about_command))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ ARIA Bot is LIVE! Open Telegram and message @JannieOpsBEATbot")
    print("Press Ctrl+C to stop.\n")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
