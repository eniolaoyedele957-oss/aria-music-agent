"""
ARIA — AI Music Agent Web App by JannieOps
==========================================
Flask backend that powers the ARIA website
"""

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import time
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────

AUDIERA_API_KEY = os.getenv("AUDIERA_API_KEY", "sk_audiera_un3w4d29ccex1tyftott8fs8130qbjfx")
WALLET_ADDRESS  = "0x034ee3E5E43D3556ee6A598089402bbA9eA8E189"

AI_PROVIDERS = [
    {
        "name": "Groq",
        "api_key": os.getenv("GROQ_API_KEY", ""),
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "headers_fn": lambda key: {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
    },
    {
        "name": "OpenRouter",
        "api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "headers_fn": lambda key: {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aria.jannieops.com",
            "X-Title": "ARIA Music Agent"
        }
    },
    {
        "name": "Gemini",
        "api_key": os.getenv("GEMINI_API_KEY", ""),
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model": "gemini-2.0-flash",
        "headers_fn": lambda key: {"Content-Type": "application/json"}
    }
]

ARTISTS = {
    "kira":         "osipvytdvxuzci9pn2nz1",
    "ray":          "jyjcnj6t3arzzb5dnzk4p",
    "jason miller": "i137z0bj0cwsbzrzd8m0c",
    "dylan cross":  "xa6h1wjowcyvo1r87x1np",
    "rhea monroe":  "yinjs025l733tttxgy2w5",
    "talia brooks": "hcqa005jz02ikis7xt2q4",
    "leo martin":   "udst8rsngyccqh3e2y80a",
    "briana rose":  "tzuww7dbsh4enwifaptfl",
}

STYLES = [
    "Pop", "Rock", "Hip-Hop", "Country", "Dance", "Electronic",
    "Disco", "Blues", "Jazz", "Folk", "Latin", "Metal", "Punk",
    "R&B", "Soul", "Funk", "Reggae", "Indie", "Afrobeat", "Classical"
]

BEAT_EARNED = 0

ARIA_SYSTEM_PROMPT = """You are ARIA, an AI music agent created by JannieOps for the Audiera platform.

Your personality:
- Creative, energetic, and passionate about music
- Enthusiastic about Web3 and the $BEAT token economy
- You speak like a cool music producer — confident and fun
- You use music emojis naturally

When generating lyrics:
- Make them emotional, powerful, and genre-appropriate
- Include [Intro], [Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Outro] sections
- Always end with a line that mentions ARIA or JannieOps

Keep responses energetic and creative!"""


# ─────────────────────────────────────────
# AI PROVIDER WITH FALLBACK
# ─────────────────────────────────────────

def call_ai(prompt):
    for provider in AI_PROVIDERS:
        if not provider["api_key"]:
            continue
        try:
            if provider["name"] == "Gemini":
                resp = requests.post(
                    f"{provider['url']}?key={provider['api_key']}",
                    json={"contents": [{"role": "user", "parts": [{"text": f"{ARIA_SYSTEM_PROMPT}\n\n{prompt}"}]}]},
                    timeout=30
                )
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                resp = requests.post(
                    provider["url"],
                    headers=provider["headers_fn"](provider["api_key"]),
                    json={
                        "model": provider["model"],
                        "messages": [
                            {"role": "system", "content": ARIA_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        "max_tokens": 1000,
                        "temperature": 0.8
                    },
                    timeout=30
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"{provider['name']} failed: {e}")
            continue
    return None


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
                return data["data"]["lyrics"]
    except Exception as e:
        print(f"Audiera lyrics error: {e}")
    return None


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

        for attempt in range(60):
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

        return None, "Song generation timed out"
    except Exception as e:
        return None, str(e)


# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html",
                           styles=STYLES,
                           artists=[a.title() for a in ARTISTS.keys()])


@app.route("/api/config")
def config():
    return jsonify({
        "audiera_api_key": AUDIERA_API_KEY,
        "wallet": WALLET_ADDRESS,
        "artists": ARTISTS,
        "styles": STYLES
    })


@app.route("/proxy/lyrics", methods=["POST"])
def proxy_lyrics():
    """Proxy lyrics request to Audiera"""
    data = request.json
    try:
        resp = requests.post(
            "https://ai.audiera.fi/api/skills/lyrics",
            headers={"Authorization": f"Bearer {AUDIERA_API_KEY}", "Content-Type": "application/json"},
            json=data,
            timeout=30
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/proxy/music", methods=["POST"])
def proxy_music():
    """Proxy music creation request to Audiera"""
    data = request.json
    try:
        resp = requests.post(
            "https://ai.audiera.fi/api/skills/music",
            headers={"Authorization": f"Bearer {AUDIERA_API_KEY}", "Content-Type": "application/json"},
            json=data,
            timeout=30
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/proxy/music/<task_id>", methods=["GET"])
def proxy_music_poll(task_id):
    """Proxy music polling request to Audiera"""
    try:
        resp = requests.get(
            f"https://ai.audiera.fi/api/skills/music/{task_id}",
            headers={"Authorization": f"Bearer {AUDIERA_API_KEY}"},
            timeout=30
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    global BEAT_EARNED

    data = request.json
    topic   = data.get("topic", "").strip()
    style   = data.get("style", "Afrobeat")
    artist  = data.get("artist", "kira").lower()

    if not topic:
        return jsonify({"error": "Please enter a topic!"}), 400

    artist_id = ARTISTS.get(artist, ARTISTS["kira"])

    def stream():
        # STEP 1: Lyrics
        yield f"data: {json.dumps({'step': 1, 'status': 'generating_lyrics', 'message': '📝 Writing fire lyrics...'})}\n\n"

        lyrics = generate_lyrics_audiera(topic, style)
        if not lyrics:
            lyrics = call_ai(f"Write powerful {style} lyrics about: {topic}. Include [Intro], [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]. End with a line mentioning ARIA or JannieOps.")

        if not lyrics:
            yield f"data: {json.dumps({'error': 'Could not generate lyrics. Please try again!'})}\n\n"
            return

        yield f"data: {json.dumps({'step': 1, 'status': 'lyrics_done', 'message': '✅ Lyrics created!', 'lyrics': lyrics})}\n\n"

        # STEP 2: Music
        yield f"data: {json.dumps({'step': 2, 'status': 'generating_music', 'message': '🎵 Creating your song on Audiera (1-3 mins)...'})}\n\n"

        songs, error = create_song_audiera(lyrics, style, artist_id)

        if error or not songs:
            yield f"data: {json.dumps({'error': error or 'Song generation failed'})}\n\n"
            return

        # STEP 3: Earn
        BEAT_EARNED += len(songs)
        songs_data = [{"title": s.get("title", "Untitled"), "url": s.get("url", ""), "duration": s.get("duration", 0)} for s in songs]

        yield f"data: {json.dumps({'step': 3, 'status': 'complete', 'message': '💰 $BEAT tokens earned!', 'songs': songs_data, 'beat_earned': BEAT_EARNED, 'wallet': WALLET_ADDRESS})}\n\n"

    return Response(stream_with_context(stream()), mimetype="text/event-stream")


@app.route("/api/wallet")
def wallet():
    return jsonify({
        "address": WALLET_ADDRESS,
        "network": "BNB Chain",
        "beat_earned": BEAT_EARNED
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)