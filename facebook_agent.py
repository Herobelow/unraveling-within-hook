"""
Autonomous Facebook Page Agent & Scheduled Content Pusher ("Bolt").
------------------------------------------------------------------
1. Pushes ANY content you give it (exact text, links, photos, videos, or AI-polished drafts)
   every N minutes or N hours.
2. Auto-drops a "First Comment" (e.g., your promo link) right under each new post so
   Facebook's algorithm doesn't penalize your main post's reach.
3. Replies to Page comments & Messenger DMs automatically (works via Meta Webhook OR
   Zero-Setup Comment Polling using only PAGE_ID + PAGE_TOKEN!).
4. Includes a built-in Live Web Control Panel ("in your face" dashboard) at http://localhost:5000
   plus CLI flags for one-line terminal operation.

Install:
    pip install anthropic flask requests python-dotenv

Run Web Dashboard + Auto-Scheduler:
    python3 facebook_agent.py

Optional CLI Quick-Commands:
    python3 facebook_agent.py --every 5                        # Run & push every 5 minutes
    python3 facebook_agent.py --push "Hello world!"            # Push a single post right now
    python3 facebook_agent.py --add "Queued post text"         # Add a post to the queue
"""

import os
import re
import sys
import json
import hmac
import time
import uuid
import hashlib
import argparse
import threading
import subprocess
from datetime import datetime, timezone


def _ensure_dependencies():
    try:
        import flask  # noqa: F401
        import requests  # noqa: F401
    except ImportError:
        print("⚡ Installing required packages (flask, requests, anthropic, python-dotenv)...")
        cmd = [sys.executable, "-m", "pip", "install", "-q", "flask", "requests", "anthropic", "python-dotenv"]
        try:
            subprocess.check_call(cmd + ["--break-system-packages"])
        except Exception:
            subprocess.check_call(cmd)


_ensure_dependencies()

import requests
from flask import Flask, request, abort, jsonify, Response

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    anthropic = None

# =============================================================================
# EDIT THIS: Tell the agent who it is and what to do.
# =============================================================================
INSTRUCTIONS = """
You manage the Facebook Page "Little Wings" — Digital Creator | Social Media Growth Expert | Helping you turn content into cash 💰.

Goals:
1. Spark lively conversation among creators, business owners, and side-hustlers who want to grow their audience and monetize their content.
2. Make people want to follow Little Wings, share our posts, and tag creator friends.
3. Naturally invite engaged followers to DM us or check out our growth resources (about 1 in 3 replies when relevant).

Voice: Energetic, encouraging, street-smart, and practical. Short punchy sentences, max 1-2 emojis (💰🔥🚀✨). Always use the person's first name when replying.

Topics We Own:
- Turning views & followers into real cash 💰
- High-retention hooks, Reels, and daily posting consistency
- Audience growth, engagement hacks, and digital product / creator monetization

Rules:
- Answer what the person actually said first, then ask one short, easy-to-answer follow-up question (e.g., "What niche are you creating in right now?" or "Are you focusing more on Reels or posts this week?").
- Never invent fake income claims, prices, or promises. If someone asks about 1-on-1 coaching or pricing, tell them to send us a DM with the word "GROWTH" and our team will hook them up.
- Never repeat the same phrase twice in a row.
- Spam, crypto/forex bots, insults, trolls -> skip.
- Complaints, refunds, billing, or sensitive topics -> escalate.
- Reply in the same language as the person. Keep comment replies under 40 words.
"""
# =============================================================================

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
GRAPH = "https://graph.facebook.com/v19.0"

STATE_FILE = os.environ.get("STATE_FILE", "facebook_agent_state.json")
CONTENT_TXT_FILE = os.environ.get("CONTENT_TXT_FILE", "content.txt")
ENV_FILE = ".env"

DEFAULT_MINUTES = float(os.environ.get("POST_EVERY_MINUTES", "0"))
DEFAULT_HOURS = float(os.environ.get("POST_EVERY_HOURS", "0"))
if DEFAULT_MINUTES <= 0 and DEFAULT_HOURS > 0:
    INITIAL_INTERVAL_MINUTES = DEFAULT_HOURS * 60.0
elif DEFAULT_MINUTES > 0:
    INITIAL_INTERVAL_MINUTES = DEFAULT_MINUTES
else:
    INITIAL_INTERVAL_MINUTES = 60.0  # default 60 minutes (1 hour)

app = Flask(__name__)


@app.after_request
def add_preview_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers.pop("X-Frame-Options", None)
    return response


# ----------------------------------------------------------------------------
# Persistent State & Queue Management
# ----------------------------------------------------------------------------
state_lock = threading.Lock()
seen_ids = set()
chat_memory = {}
MAX_MEMORY = 12
MAX_LOGS = 120

state = {
    "config": {
        "page_id": os.environ.get("PAGE_ID", ""),
        "page_token": os.environ.get("PAGE_TOKEN", ""),
        "app_id": os.environ.get("APP_ID", ""),
        "app_secret": os.environ.get("APP_SECRET", ""),
        "verify_token": os.environ.get("VERIFY_TOKEN", "my-secret-verify-token"),
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "dry_run": os.environ.get("DRY_RUN", "true").lower() != "false",
        "scheduler_enabled": True,
        "interval_minutes": INITIAL_INTERVAL_MINUTES,
        "loop_queue": True,            # recycle content when queue finishes
        "ai_fallback": False,          # generate AI starter if queue is empty
        "poll_comments": True,         # zero-webhook comment polling
        "poll_every_minutes": 0.5,     # check for new comments every 30 seconds
        "instructions": INSTRUCTIONS.strip(),
    },
    "queue": [],
    "logs": [],
    "stats": {
        "posts_sent": 0,
        "comments_replied": 0,
        "messages_replied": 0,
        "escalations": 0,
    },
    "next_run_ts": time.time() + (INITIAL_INTERVAL_MINUTES * 60.0),
    "last_run_ts": None,
    "next_poll_ts": time.time() + 15.0,
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def add_log(level, category, message, details=None):
    entry = {
        "id": str(uuid.uuid4())[:8],
        "time": now_iso(),
        "level": level,         # info | success | warning | error
        "category": category,   # scheduler | facebook | comment | message | system
        "message": message,
        "details": details or "",
    }
    print(f"[{entry['time']}] [{category.upper()}] {message} {details or ''}".strip())
    with state_lock:
        state["logs"].insert(0, entry)
        del state["logs"][MAX_LOGS:]


def persist_env_credentials():
    """Keep .env updated when user saves credentials in the Web UI."""
    with state_lock:
        cfg = dict(state["config"])
    lines = [
        "# Auto-saved by Bolt Facebook Page Agent",
        f"PAGE_ID={cfg.get('page_id', '')}",
        f"PAGE_TOKEN={cfg.get('page_token', '')}",
        f"APP_SECRET={cfg.get('app_secret', '')}",
        f"VERIFY_TOKEN={cfg.get('verify_token', 'my-secret-verify-token')}",
        f"ANTHROPIC_API_KEY={cfg.get('anthropic_api_key', '')}",
        f"POST_EVERY_MINUTES={cfg.get('interval_minutes', 60)}",
        f"DRY_RUN={'true' if cfg.get('dry_run', True) else 'false'}",
    ]
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        print("Could not write .env:", e)


def save_state():
    """Save queue, logs, stats, seen_ids, and preferences to disk."""
    with state_lock:
        payload = {
            "config": {
                "page_id": state["config"]["page_id"],
                "verify_token": state["config"]["verify_token"],
                "dry_run": state["config"]["dry_run"],
                "scheduler_enabled": state["config"]["scheduler_enabled"],
                "interval_minutes": state["config"]["interval_minutes"],
                "loop_queue": state["config"]["loop_queue"],
                "ai_fallback": state["config"]["ai_fallback"],
                "poll_comments": state["config"]["poll_comments"],
                "poll_every_minutes": state["config"]["poll_every_minutes"],
                "instructions": state["config"]["instructions"],
            },
            "queue": state["queue"],
            "logs": state["logs"][:60],
            "stats": state["stats"],
            "seen_ids": list(seen_ids)[-500:],
            "last_run_ts": state["last_run_ts"],
        }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print("Could not save state file:", e)


def load_content_txt_if_needed():
    """Load initial posts from content.txt if queue is empty."""
    if not os.path.exists(CONTENT_TXT_FILE):
        sample = (
            "# Put one post per block (separated by a line with ---)\n"
            "# Lines starting with # are ignored.\n"
            "---\n"
            "Quick question for everyone here: What is the #1 tool or habit you can't live without this week? Drop it below!\n"
            "---\n"
            "Behind the scenes update! We're working on something special for our community. Stay tuned and let us know what you want to see next!\n"
            "---\n"
            "Hot take time: Consistency beats intensity 100% of the time. Agree or disagree?\n"
        )
        try:
            with open(CONTENT_TXT_FILE, "w", encoding="utf-8") as f:
                f.write(sample)
        except Exception:
            return

    try:
        with open(CONTENT_TXT_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
        cleaned = "\n".join(
            line for line in raw.splitlines()
            if not line.strip().startswith("#")
        )
        blocks = [b.strip() for b in re.split(r"(?m)^\s*---\s*$", cleaned) if b.strip()]
        if blocks and not state["queue"]:
            for b in blocks:
                state["queue"].append({
                    "id": str(uuid.uuid4())[:8],
                    "text": b,
                    "link": "",
                    "image_url": "",
                    "video_url": "",
                    "first_comment": "",
                    "mode": "exact",  # exact | polish
                    "status": "pending",
                    "runs": 0,
                    "last_posted": None,
                })
            add_log("info", "system", f"Loaded {len(blocks)} starter post(s) from {CONTENT_TXT_FILE}")
    except Exception as e:
        print("Error reading content.txt:", e)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            with state_lock:
                cfg = saved.get("config", {})
                for k in (
                    "dry_run",
                    "scheduler_enabled",
                    "interval_minutes",
                    "loop_queue",
                    "ai_fallback",
                    "poll_comments",
                    "poll_every_minutes",
                    "instructions",
                ):
                    if k in cfg:
                        state["config"][k] = cfg[k]
                if not state["config"]["page_id"] and cfg.get("page_id"):
                    state["config"]["page_id"] = cfg["page_id"]
                state["queue"] = saved.get("queue", [])
                state["logs"] = saved.get("logs", [])
                state["stats"].update(saved.get("stats", {}))
                for sid in saved.get("seen_ids", []):
                    seen_ids.add(sid)
                state["last_run_ts"] = saved.get("last_run_ts")
                state["next_run_ts"] = time.time() + float(state["config"]["interval_minutes"]) * 60.0
        except Exception as e:
            print("Failed to load saved state:", e)
    load_content_txt_if_needed()


# ----------------------------------------------------------------------------
# AI Brain (Works with ZERO Key, OR Free Groq / Gemini / OpenAI / Anthropic!)
# ----------------------------------------------------------------------------
def get_ai_key():
    return (
        state["config"].get("anthropic_api_key")
        or os.environ.get("AI_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    ).strip()


def detect_ai_provider(key=""):
    key = (key or get_ai_key()).strip()
    if not key:
        return "builtin_free"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("sk-"):
        return "openai"
    return "groq"


def builtin_smart_brain(event_type, author, content, context=""):
    """
    100% Free Built-In Smart Brain that requires NO API key at all!
    Handles comments, DMs, post polishing, and conversation starters automatically.
    """
    first_name = (author or "friend").strip().split()[0]
    if first_name.lower() in ("the", "there", "user", "page", "anonymous"):
        first_name = "friend"

    text_lower = (content or "").lower().strip()

    # 1. Polish a post draft
    if event_type == "polish_post":
        cleaned = (content or "").strip()
        if "?" not in cleaned:
            cleaned = f"🔥 {cleaned}\n\nWhat are your thoughts on this? Drop a comment below! 👇"
        else:
            cleaned = f"✨ {cleaned}"
        return {"action": "post", "text": cleaned, "reason": "Polished with Built-in Free Brain"}

    # 2. Generate a conversation starter
    if event_type == "conversation_starter":
        starters = [
            "Quick question for our community today: What is one goal you are focusing on this week? Drop it below! 👇",
            "Hot take: Consistency beats motivation 100% of the time. Do you agree or disagree? 🔥",
            "If you could master one skill overnight, what would you pick and why? Let's chat in the comments!",
            "What's the best piece of advice you've ever received? Share it below to inspire someone today! 🙌",
        ]
        pick = starters[int(time.time()) % len(starters)]
        return {"action": "post", "text": pick, "reason": "Built-in conversation starter"}

    # 3. Filter empty / spam / trolls
    if not text_lower or any(w in text_lower for w in ("http://", "https://", "crypto", "forex", "whatsapp me")):
        return {"action": "skip", "text": "", "reason": "Filtered potential spam/link"}

    # 4. Escalate complaints / refunds / sensitive topics
    if any(w in text_lower for w in ("refund", "scam", "angry", "lawsuit", "terrible", "worst", "complaint", "broken")):
        return {
            "action": "escalate",
            "text": "",
            "reason": "Customer complaint or refund keyword detected",
        }

    # 5. Extract any link from instructions if user asks for link/info/price
    instructions_text = state["config"].get("instructions", "")
    urls = [u for u in re.findall(r"https?://[^\s\)\]]+", instructions_text) if "URL" not in u]
    promo_url = urls[0] if urls else ""

    if any(w in text_lower for w in ("link", "website", "video", "where", "how much", "price", "cost", "buy", "info", "details", "help")):
        if promo_url:
            reply = f"Hey {first_name}! 😊 Thanks for asking! You can check out the details right here: {promo_url} — what part are you most interested in?"
        else:
            reply = f"Hey {first_name}! 😊 Great question! Our team is sending you the full details shortly. What specific goal are you looking to achieve?"
        return {"action": "reply", "text": reply, "reason": "Answered question with Built-in Smart Brain"}

    # 6. Friendly conversational reply to comments & DMs
    replies = [
        f"Appreciate you jumping in, {first_name}! 🙌 What's been your favorite part so far?",
        f"So glad you're here, {first_name}! 😊 Tell us—what would you love to see us post about next?",
        f"Love this, {first_name}! 🔥 How long have you been following along with this topic?",
        f"Thanks so much for sharing, {first_name}! 🙌 Do you have a #1 tip you'd add to this?",
    ]
    pick = replies[sum(ord(c) for c in (content or "a")) % len(replies)]
    return {"action": "reply", "text": pick, "reason": "Replied with Built-in Free Smart Brain"}


def call_llm_json(sys_prompt, messages):
    """Calls whichever AI provider matches the user's key (Groq, Gemini, OpenAI, or Anthropic)."""
    key = get_ai_key()
    provider = detect_ai_provider(key)

    if provider == "groq":
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "system", "content": sys_prompt}] + messages,
                "temperature": 0.7,
                "max_tokens": 500,
            },
            timeout=25,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    if provider == "gemini":
        combined = sys_prompt + "\n\n" + "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": combined}]}]},
            timeout=25,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    if provider == "openai":
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "system", "content": sys_prompt}] + messages,
                "temperature": 0.7,
                "max_tokens": 500,
            },
            timeout=25,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    if provider == "anthropic" and anthropic is not None:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=MODEL, max_tokens=500, system=sys_prompt, messages=messages
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    return ""


def think(event_type, author, content, context="", history=None):
    key = get_ai_key()
    if not key:
        return builtin_smart_brain(event_type, author, content, context=context)

    messages = list(history or [])
    messages.append({
        "role": "user",
        "content": f"EVENT_TYPE: {event_type}\nAUTHOR: {author}\nCONTENT: {content}\nCONTEXT: {context}",
    })

    sys_prompt = state["config"].get("instructions", INSTRUCTIONS) + """

You will receive one event at a time in this format:
EVENT_TYPE: new_comment | new_message | conversation_starter | polish_post
AUTHOR: name
CONTENT: the text or draft
CONTEXT: related post text or instructions, if any

Respond with JSON only, no other text:
{"action": "reply" | "post" | "skip" | "escalate", "text": "<your message>", "reason": "<short note>"}
"""
    try:
        raw = call_llm_json(sys_prompt, messages).strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        add_log("warning", "system", f"External AI key error ({e}); using Built-in Free Brain fallback.")
        return builtin_smart_brain(event_type, author, content, context=context)


def generate_bulk_posts(topic, count=5):
    """Generate `count` ready-to-queue posts about `topic` using any configured AI key or built-in templates."""
    count = max(1, min(20, int(count)))
    key = get_ai_key()
    if key:
        prompt = (
            f"Create {count} distinct, high-engagement Facebook Page posts about: {topic}.\n"
            "Follow our Page instructions and voice. Make each post punchy, human, and end with a question.\n"
            "Return ONLY a JSON array of strings, e.g. [\"Post 1...\", \"Post 2...\"]"
        )
        try:
            raw = call_llm_json(
                state["config"].get("instructions", INSTRUCTIONS),
                [{"role": "user", "content": prompt}],
            ).strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
            arr = json.loads(raw)
            if isinstance(arr, list) and arr:
                return [str(x).strip() for x in arr if str(x).strip()][:count]
        except Exception as e:
            add_log("warning", "system", "AI bulk generation fell back to built-in templates", str(e))

    # Smart built-in templates when no Anthropic key is configured
    templates = [
        f"Let's talk about {topic}! What's the biggest lesson you've learned so far? 👇",
        f"Unpopular opinion on {topic}: Keeping it simple beats overcomplicating it every single time. Do you agree or disagree?",
        f"Quick tip for anyone focusing on {topic} today: Start with one small win before noon. What's your #1 priority today?",
        f"If you could give one piece of advice to a beginner starting out with {topic}, what would you tell them?",
        f"This or That ({topic} edition): Do you prefer planning everything ahead or learning as you go? Drop your vote below!",
        f"Behind the scenes: We've been diving deep into {topic} this week. What's your biggest question about it right now?",
        f"Tag a friend who needs to see this reminder about {topic} today! 🔥",
    ]
    results = []
    for i in range(count):
        results.append(templates[i % len(templates)])
    return results


# ----------------------------------------------------------------------------
# Facebook Graph API Actions
# ----------------------------------------------------------------------------
def fb_post(path, data):
    dry_run = state["config"]["dry_run"]
    page_token = state["config"]["page_token"]

    if dry_run:
        fake_id = f"dryrun_{int(time.time() * 1000)}"
        add_log("info", "facebook", f"[DRY RUN] Would POST to /{path}", json.dumps(data))
        return {"dry_run": True, "id": fake_id}

    if not page_token:
        add_log("error", "facebook", f"Cannot POST to /{path}: PAGE_TOKEN is missing!", "Set PAGE_TOKEN in settings or .env")
        return {"error": "Missing PAGE_TOKEN"}

    payload = dict(data, access_token=page_token)
    try:
        r = requests.post(f"{GRAPH}/{path}", data=payload, timeout=12)
        resp_json = r.json() if r.content else {}
        if not r.ok:
            add_log("error", "facebook", f"Facebook API error ({r.status_code}) on /{path}", r.text)
        else:
            add_log("success", "facebook", f"Published to Facebook /{path}", json.dumps(resp_json))
        return resp_json
    except Exception as e:
        # Signal to the browser dashboard that it should execute the Graph API call directly from the user's browser
        return {"browser_fallback": True, "path": path, "data": data, "error": str(e)}


def publish_content_item(text, link="", image_url="", video_url="", first_comment=""):
    """Publish text, link, photo, or video to the Facebook Page, plus optional First Comment."""
    page_id = state["config"]["page_id"] or "me"
    if video_url:
        data = {"file_url": video_url, "description": text}
        if link:
            data["description"] = f"{text}\n\n{link}".strip()
        res = fb_post(f"{page_id}/videos", data)
    elif image_url:
        data = {"url": image_url, "caption": text}
        if link:
            data["caption"] = f"{text}\n\n{link}".strip()
        res = fb_post(f"{page_id}/photos", data)
    else:
        data = {"message": text}
        if link:
            data["link"] = link
        res = fb_post(f"{page_id}/feed", data)

    with state_lock:
        state["stats"]["posts_sent"] += 1

    # Auto-drop First Comment if provided and post succeeded
    post_id = res.get("post_id") or res.get("id")
    if first_comment and post_id and "error" not in res:
        fb_post(f"{post_id}/comments", {"message": first_comment})
        add_log("success", "facebook", f"Auto-dropped First Comment on post {post_id}: \"{first_comment[:60]}\"")

    return res


def reply_to_comment(comment_id, text):
    res = fb_post(f"{comment_id}/comments", {"message": text})
    with state_lock:
        state["stats"]["comments_replied"] += 1
    return res


def send_message(recipient_id, text):
    res = fb_post(
        "me/messages",
        {
            "recipient": json.dumps({"id": recipient_id}),
            "message": json.dumps({"text": text}),
            "messaging_type": "RESPONSE",
        },
    )
    with state_lock:
        state["stats"]["messages_replied"] += 1
    return res


def alert_owner(kind, who, content, reason):
    with state_lock:
        state["stats"]["escalations"] += 1
    add_log("warning", kind, f"ESCALATED ({kind}) from {who}: {content}", f"Reason: {reason}")


# ----------------------------------------------------------------------------
# Content Pusher Engine (Runs every N minutes/hours or on-demand)
# ----------------------------------------------------------------------------
def push_next_content(specific_id=None):
    """
    Picks the next pending item from the queue (or a specific item by ID),
    processes it (exact or AI-polished), and pushes it to Facebook.
    """
    item = None
    with state_lock:
        if specific_id:
            for q in state["queue"]:
                if q["id"] == specific_id:
                    item = q
                    break
        else:
            for q in state["queue"]:
                if q.get("status") == "pending":
                    item = q
                    break
            if item is None and state["config"].get("loop_queue") and state["queue"]:
                for q in state["queue"]:
                    q["status"] = "pending"
                item = state["queue"][0]
                add_log("info", "scheduler", "Queue finished a full cycle — looping back to the first item.")

    if item is not None:
        raw_text = item.get("text", "").strip()
        mode = item.get("mode", "exact")
        final_text = raw_text

        if mode == "polish":
            d = think(
                "polish_post",
                "Page Owner",
                raw_text,
                context="Rewrite/polish this draft into an engaging Facebook Page post following our brand voice. Keep any links intact.",
            )
            if d.get("text"):
                final_text = d["text"]

        res = publish_content_item(
            text=final_text,
            link=item.get("link", "").strip(),
            image_url=item.get("image_url", "").strip(),
            video_url=item.get("video_url", "").strip(),
            first_comment=item.get("first_comment", "").strip(),
        )

        with state_lock:
            item["runs"] = item.get("runs", 0) + 1
            item["last_posted"] = now_iso()
            item["status"] = "posted"
            state["last_run_ts"] = time.time()
            interval_sec = max(10.0, float(state["config"]["interval_minutes"]) * 60.0)
            state["next_run_ts"] = time.time() + interval_sec

        add_log(
            "success",
            "scheduler",
            f"Pushed queued item #{item['id']} ({mode} mode): \"{final_text[:80]}{'...' if len(final_text) > 80 else ''}\"",
        )
        save_state()
        return {"ok": True, "item": item, "final_text": final_text, "fb_result": res}

    if state["config"].get("ai_fallback"):
        d = think(
            "conversation_starter",
            "Page",
            "Write a fresh conversation-starter post (a question, this-or-that, or hot take). No links.",
        )
        if d.get("action") == "post" and d.get("text"):
            res = publish_content_item(d["text"])
            with state_lock:
                state["last_run_ts"] = time.time()
                interval_sec = max(10.0, float(state["config"]["interval_minutes"]) * 60.0)
                state["next_run_ts"] = time.time() + interval_sec
            add_log("success", "scheduler", f"Pushed AI conversation-starter: \"{d['text'][:80]}\"")
            save_state()
            return {"ok": True, "final_text": d["text"], "fb_result": res}

    with state_lock:
        interval_sec = max(10.0, float(state["config"]["interval_minutes"]) * 60.0)
        state["next_run_ts"] = time.time() + interval_sec
    add_log("info", "scheduler", "Scheduled tick ran, but no pending items in queue (add content or enable Loop/AI Fallback).")
    return {"ok": False, "reason": "No pending content in queue"}


# ----------------------------------------------------------------------------
# Zero-Webhook Comment Poller (Works with just PAGE_ID + PAGE_TOKEN!)
# ----------------------------------------------------------------------------
def poll_page_comments():
    """Fetch recent comments on the Page's posts via Graph API and handle any unseen ones."""
    page_token = state["config"].get("page_token", "")
    page_id = state["config"].get("page_id") or "me"
    if not page_token:
        return {"ok": False, "reason": "No PAGE_TOKEN configured"}

    try:
        r = requests.get(
            f"{GRAPH}/{page_id}/posts",
            params={
                "fields": "id,message,comments.limit(10){id,from,message,created_time}",
                "limit": 5,
                "access_token": page_token,
            },
            timeout=20,
        )
        if not r.ok:
            return {"ok": False, "error": r.text}
        data = r.json()
        new_count = 0
        for post in data.get("data", []):
            post_id = post.get("id", "")
            post_msg = post.get("message", "")
            for c in post.get("comments", {}).get("data", []):
                cid = c.get("id")
                if cid and cid not in seen_ids:
                    new_count += 1
                    handle_comment({
                        "comment_id": cid,
                        "from": c.get("from", {}),
                        "message": c.get("message", ""),
                        "post_id": post_id,
                        "post_message": post_msg,
                    })
        return {"ok": True, "new_comments": new_count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def background_worker_loop():
    """Unified background loop for scheduled content pushing + optional comment polling."""
    while True:
        time.sleep(1)
        should_fire_post = False
        should_poll_comments = False

        with state_lock:
            now = time.time()
            if state["config"].get("scheduler_enabled", True) and now >= state.get("next_run_ts", 0):
                should_fire_post = True
                interval_sec = max(10.0, float(state["config"]["interval_minutes"]) * 60.0)
                state["next_run_ts"] = now + interval_sec

            if (
                state["config"].get("poll_comments", True)
                and state["config"].get("page_token")
                and now >= state.get("next_poll_ts", 0)
            ):
                should_poll_comments = True
                poll_sec = max(30.0, float(state["config"].get("poll_every_minutes", 2.0)) * 60.0)
                state["next_poll_ts"] = now + poll_sec

        if should_fire_post:
            try:
                push_next_content()
            except Exception as e:
                add_log("error", "scheduler", "Scheduler error", str(e))

        if should_poll_comments:
            try:
                poll_page_comments()
            except Exception as e:
                add_log("error", "comment", "Comment poller error", str(e))


# ----------------------------------------------------------------------------
# Event Handlers (Comments & Messenger)
# ----------------------------------------------------------------------------
def handle_comment(value):
    comment_id = value.get("comment_id")
    sender = value.get("from", {})
    if not comment_id or comment_id in seen_ids:
        return
    seen_ids.add(comment_id)
    if sender.get("id") and sender.get("id") == state["config"]["page_id"]:
        add_log(
            "info",
            "comment",
            "Skipped comment made by the Page itself (Tip: switch to your personal Facebook profile to test commenting!).",
        )
        return

    author_name = sender.get("name", "friend")
    comment_text = value.get("message", "")
    add_log("info", "comment", f"Incoming comment from {author_name}: \"{comment_text}\"")

    context_str = f"post_id: {value.get('post_id', '')}"
    if value.get("post_message"):
        context_str += f" | post_text: {value.get('post_message')[:160]}"

    decision = think(
        "new_comment",
        author_name,
        comment_text,
        context=context_str,
    )
    act = decision.get("action")
    if act == "reply" and decision.get("text"):
        reply_to_comment(comment_id, decision["text"])
        add_log("success", "comment", f"Replied to {author_name}: \"{decision['text']}\"")
    elif act == "escalate":
        alert_owner("comment", author_name, comment_text, decision.get("reason"))
    else:
        add_log("info", "comment", f"Skipped comment {comment_id}", decision.get("reason"))
    save_state()


def handle_message(event):
    sender_id = event.get("sender", {}).get("id", "")
    msg = event.get("message", {})
    if msg.get("is_echo") or (sender_id and sender_id == state["config"]["page_id"]) or "text" not in msg:
        return
    mid = msg.get("mid") or str(uuid.uuid4())
    if mid in seen_ids:
        return
    seen_ids.add(mid)

    user_text = msg["text"]
    add_log("info", "message", f"Incoming DM from {sender_id}: \"{user_text}\"")

    history = chat_memory.setdefault(sender_id, [])
    decision = think("new_message", "the user", user_text, history=history)

    history.append({"role": "user", "content": user_text})
    if decision.get("action") == "reply" and decision.get("text"):
        history.append({"role": "assistant", "content": decision["text"]})
        send_message(sender_id, decision["text"])
        add_log("success", "message", f"Sent DM reply to {sender_id}: \"{decision['text']}\"")
    elif decision.get("action") == "escalate":
        alert_owner("message", sender_id, user_text, decision.get("reason"))
    else:
        add_log("info", "message", f"Skipped DM from {sender_id}", decision.get("reason"))

    del history[:-MAX_MEMORY]
    while history and history[0]["role"] != "user":
        history.pop(0)
    save_state()


# ----------------------------------------------------------------------------
# Meta Webhook Endpoints
# ----------------------------------------------------------------------------
@app.get("/webhook")
def verify():
    verify_token = state["config"]["verify_token"]
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == verify_token
    ):
        add_log("success", "system", "Webhook verified by Meta!")
        return request.args.get("hub.challenge", ""), 200
    abort(403)


@app.post("/webhook")
def receive():
    app_secret = state["config"]["app_secret"]
    if app_secret:
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(app_secret.encode(), request.data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            add_log("error", "system", "Rejected webhook request: invalid X-Hub-Signature-256")
            abort(403)

    body = request.get_json(silent=True) or {}
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            v = change.get("value", {})
            if change.get("field") == "feed" and v.get("item") == "comment" and v.get("verb") == "add":
                threading.Thread(target=handle_comment, args=(v,), daemon=True).start()
        for event in entry.get("messaging", []):
            threading.Thread(target=handle_message, args=(event,), daemon=True).start()
    return "ok", 200


# ----------------------------------------------------------------------------
# Control Panel REST API
# ----------------------------------------------------------------------------
@app.get("/api/state")
def api_get_state():
    with state_lock:
        cfg = state["config"]
        remaining = max(0, int(state["next_run_ts"] - time.time()))
        return jsonify({
            "config": {
                "page_id": cfg["page_id"],
                "page_token": cfg["page_token"],
                "has_page_token": bool(cfg["page_token"]),
                "page_token_preview": (cfg["page_token"][:6] + "..." + cfg["page_token"][-4:]) if len(cfg["page_token"]) > 12 else ("Set" if cfg["page_token"] else ""),
                "has_app_secret": bool(cfg["app_secret"]),
                "verify_token": cfg["verify_token"],
                "has_anthropic_key": bool(cfg["anthropic_api_key"] or os.environ.get("ANTHROPIC_API_KEY")),
                "dry_run": cfg["dry_run"],
                "scheduler_enabled": cfg["scheduler_enabled"],
                "interval_minutes": cfg["interval_minutes"],
                "loop_queue": cfg["loop_queue"],
                "ai_fallback": cfg["ai_fallback"],
                "poll_comments": cfg["poll_comments"],
                "instructions": cfg["instructions"],
            },
            "queue": state["queue"],
            "logs": state["logs"][:60],
            "stats": state["stats"],
            "seen_ids": list(seen_ids)[-200:],
            "seconds_until_next": remaining,
            "server_time": now_iso(),
        })


@app.post("/api/log-client")
def api_log_client():
    data = request.get_json(silent=True) or {}
    level = data.get("level", "info")
    category = data.get("category", "facebook")
    message = data.get("message", "")
    details = data.get("details", "")
    stat_inc = data.get("stat_inc")
    seen_id = data.get("seen_id")
    if seen_id:
        seen_ids.add(seen_id)
    if stat_inc:
        with state_lock:
            if stat_inc in state["stats"]:
                state["stats"][stat_inc] += 1
    if message:
        add_log(level, category, message, details)
    save_state()
    return jsonify({"ok": True})


@app.post("/api/brain-reply")
def api_brain_reply():
    data = request.get_json(silent=True) or {}
    comment_id = data.get("comment_id", "")
    author = data.get("author", "friend")
    text = data.get("text", "")
    post_message = data.get("post_message", "")
    if comment_id:
        seen_ids.add(comment_id)
    decision = think(
        "new_comment",
        author,
        text,
        context=f"post_text: {post_message[:160]}",
    )
    return jsonify({"ok": True, "decision": decision})


@app.post("/api/config")
def api_update_config():
    data = request.get_json(silent=True) or {}
    save_env = False
    with state_lock:
        cfg = state["config"]
        if "dry_run" in data:
            cfg["dry_run"] = bool(data["dry_run"])
            save_env = True
        if "scheduler_enabled" in data:
            cfg["scheduler_enabled"] = bool(data["scheduler_enabled"])
        if "interval_minutes" in data:
            mins = max(0.25, float(data["interval_minutes"]))
            cfg["interval_minutes"] = mins
            state["next_run_ts"] = time.time() + (mins * 60.0)
            save_env = True
        if "loop_queue" in data:
            cfg["loop_queue"] = bool(data["loop_queue"])
        if "ai_fallback" in data:
            cfg["ai_fallback"] = bool(data["ai_fallback"])
        if "poll_comments" in data:
            cfg["poll_comments"] = bool(data["poll_comments"])
        if "page_id" in data:
            cfg["page_id"] = str(data["page_id"]).strip()
            save_env = True
        if "page_token" in data and str(data["page_token"]).strip():
            cfg["page_token"] = str(data["page_token"]).strip()
            save_env = True
        if "app_secret" in data and str(data["app_secret"]).strip():
            cfg["app_secret"] = str(data["app_secret"]).strip()
            save_env = True
        if "verify_token" in data:
            cfg["verify_token"] = str(data["verify_token"]).strip()
            save_env = True
        if "anthropic_api_key" in data and str(data["anthropic_api_key"]).strip():
            cfg["anthropic_api_key"] = str(data["anthropic_api_key"]).strip()
            save_env = True
        if "instructions" in data:
            cfg["instructions"] = str(data["instructions"])

    if save_env:
        persist_env_credentials()

    add_log(
        "info",
        "system",
        f"Updated settings: every {state['config']['interval_minutes']} min | "
        f"Scheduler={'ON' if state['config']['scheduler_enabled'] else 'PAUSED'} | "
        f"Mode={'DRY RUN' if state['config']['dry_run'] else 'LIVE FACEBOOK'}",
    )
    save_state()
    return jsonify({"ok": True})


@app.post("/api/queue")
def api_add_queue():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "exact")
    link = str(data.get("link", "")).strip()
    image_url = str(data.get("image_url", "")).strip()
    video_url = str(data.get("video_url", "")).strip()
    first_comment = str(data.get("first_comment", "")).strip()

    raw_text = str(data.get("text", "")).strip()
    if not raw_text:
        return jsonify({"ok": False, "error": "Content text is required"}), 400

    blocks = [b.strip() for b in re.split(r"(?m)^\s*---\s*$", raw_text) if b.strip()] if data.get("bulk") else [raw_text]
    added = []
    with state_lock:
        for b in blocks:
            item = {
                "id": str(uuid.uuid4())[:8],
                "text": b,
                "link": link,
                "image_url": image_url,
                "video_url": video_url,
                "first_comment": first_comment,
                "mode": mode,
                "status": "pending",
                "runs": 0,
                "last_posted": None,
            }
            state["queue"].append(item)
            added.append(item)

    add_log("info", "scheduler", f"Added {len(added)} content item(s) to queue ({mode} mode).")
    save_state()
    return jsonify({"ok": True, "added": len(added), "items": added})


@app.post("/api/queue/generate")
def api_generate_queue():
    """Generate a batch of posts on a given topic and add them directly to the queue."""
    data = request.get_json(silent=True) or {}
    topic = str(data.get("topic", "")).strip()
    count = int(data.get("count", 5))
    first_comment = str(data.get("first_comment", "")).strip()
    if not topic:
        return jsonify({"ok": False, "error": "Topic is required"}), 400

    posts = generate_bulk_posts(topic, count=count)
    added = []
    with state_lock:
        for p in posts:
            item = {
                "id": str(uuid.uuid4())[:8],
                "text": p,
                "link": "",
                "image_url": "",
                "video_url": "",
                "first_comment": first_comment,
                "mode": "exact",
                "status": "pending",
                "runs": 0,
                "last_posted": None,
            }
            state["queue"].append(item)
            added.append(item)

    add_log("success", "scheduler", f"Generated & queued {len(added)} posts for topic: \"{topic}\"")
    save_state()
    return jsonify({"ok": True, "added": len(added), "items": added})


@app.post("/api/queue/action")
def api_queue_action():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    item_id = data.get("id")

    if action == "push_now":
        res = push_next_content(specific_id=item_id)
        return jsonify(res)

    with state_lock:
        if action == "delete":
            state["queue"] = [q for q in state["queue"] if q["id"] != item_id]
        elif action == "reset_all":
            for q in state["queue"]:
                q["status"] = "pending"
            add_log("info", "scheduler", "Reset all queue items to pending.")
        elif action == "clear_all":
            state["queue"] = []
            add_log("info", "scheduler", "Cleared all items from the queue.")
        elif action == "toggle_status":
            for q in state["queue"]:
                if q["id"] == item_id:
                    q["status"] = "pending" if q["status"] == "posted" else "posted"
    save_state()
    return jsonify({"ok": True})


@app.post("/api/simulate")
def api_simulate():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "comment")
    author = data.get("author", "Alex")
    text = data.get("text", "Hey! Can you tell me more about what you offer?")
    if kind == "comment":
        handle_comment({
            "comment_id": f"sim_comment_{int(time.time()*1000)}",
            "from": {"name": author, "id": "user_123"},
            "message": text,
            "post_id": "sim_post_1",
        })
    else:
        handle_message({
            "sender": {"id": f"sim_user_{author}"},
            "message": {"mid": f"sim_mid_{int(time.time()*1000)}", "text": text},
        })
    return jsonify({"ok": True})


@app.post("/api/poll-now")
def api_poll_now():
    res = poll_page_comments()
    if res.get("ok"):
        add_log("info", "comment", f"Checked Facebook Page for new comments (found {res.get('new_comments', 0)} new).")
    else:
        add_log("warning", "comment", "Could not check Facebook comments yet", res.get("reason") or res.get("error", ""))
    return jsonify(res)


@app.post("/api/test-fb")
def api_test_fb():
    token = state["config"]["page_token"]
    page_id = state["config"]["page_id"] or "me"
    if not token:
        return jsonify({"ok": False, "error": "No PAGE_TOKEN set yet."}), 400
    try:
        r = requests.get(f"{GRAPH}/{page_id}", params={"fields": "id,name", "access_token": token}, timeout=15)
        data = r.json()
        if r.ok and "name" in data:
            with state_lock:
                if not state["config"]["page_id"]:
                    state["config"]["page_id"] = data["id"]
            persist_env_credentials()
            add_log("success", "facebook", f"Connected to Facebook Page: {data['name']} (ID: {data['id']})")
            return jsonify({"ok": True, "page": data})
        add_log("error", "facebook", "Facebook token check failed", r.text)
        return jsonify({"ok": False, "error": data.get("error", {}).get("message", r.text)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------------------------------------------------------------
# Built-in Live Web Control Panel ("In Your Face" Dashboard)
# ----------------------------------------------------------------------------
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bolt — Facebook Page Content Pusher & AI Agent</title>
<style>
  :root {
    --bg: #0b0f19;
    --card: #131b2e;
    --card-border: #1e293b;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --primary: #3b82f6;
    --primary-hover: #2563eb;
    --green: #10b981;
    --amber: #f59e0b;
    --red: #ef4444;
    --purple: #8b5cf6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    padding: 20px;
  }
  .container { max-width: 1240px; margin: 0 auto; }
  header {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
    gap: 16px; padding-bottom: 18px; margin-bottom: 22px; border-bottom: 1px solid var(--card-border);
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .bolt-icon {
    width: 42px; height: 42px; border-radius: 10px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; font-weight: bold;
  }
  h1 { font-size: 20px; font-weight: 700; }
  .subtitle { font-size: 13px; color: var(--muted); }
  .status-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .pill {
    padding: 6px 12px; border-radius: 999px; font-size: 12px; font-weight: 600;
    display: inline-flex; align-items: center; gap: 6px; border: 1px solid transparent;
  }
  .pill.dry { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border-color: rgba(245, 158, 11, 0.35); }
  .pill.live { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.35); }
  .pill.timer { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border-color: rgba(59, 130, 246, 0.35); font-variant-numeric: tabular-nums; }

  .stats-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px; margin-bottom: 22px;
  }
  .stat-card {
    background: var(--card); border: 1px solid var(--card-border);
    border-radius: 12px; padding: 14px 18px;
  }
  .stat-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .stat-value { font-size: 26px; font-weight: 700; margin-top: 4px; }

  .main-grid {
    display: grid; grid-template-columns: 1.18fr 0.82fr; gap: 20px;
  }
  @media (max-width: 920px) { .main-grid { grid-template-columns: 1fr; } }

  .card {
    background: var(--card); border: 1px solid var(--card-border);
    border-radius: 14px; padding: 20px; margin-bottom: 20px;
  }
  .card-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 14px; gap: 10px; flex-wrap: wrap;
  }
  .card-title { font-size: 16px; font-weight: 600; }

  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; margin-top: 12px; }
  label:first-child { margin-top: 0; }
  input[type="text"], input[type="number"], input[type="password"], select, textarea {
    width: 100%; background: #090d16; border: 1px solid #26334d; color: var(--text);
    padding: 10px 12px; border-radius: 8px; font-size: 14px; font-family: inherit;
  }
  textarea { resize: vertical; min-height: 90px; }
  input:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); }

  .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .row > * { flex: 1; min-width: 150px; }

  button {
    cursor: pointer; border: none; border-radius: 8px; padding: 9px 14px;
    font-size: 13px; font-weight: 600; color: #fff; background: var(--primary);
    transition: opacity 0.15s, background 0.15s;
  }
  button:hover { background: var(--primary-hover); }
  button.secondary { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; }
  button.secondary:hover { background: #334155; }
  button.success { background: var(--green); }
  button.purple { background: var(--purple); }
  button.danger { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.35); }
  button.sm { padding: 5px 10px; font-size: 12px; }

  .preset-btns { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .preset-btns button { flex: none; }

  .queue-list { display: flex; flex-direction: column; gap: 10px; max-height: 440px; overflow-y: auto; }
  .queue-item {
    background: #090d16; border: 1px solid #1e293b; border-radius: 10px; padding: 12px;
    display: flex; justify-content: space-between; gap: 12px; align-items: flex-start;
  }
  .queue-item.posted { opacity: 0.6; }
  .queue-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
  .badge {
    font-size: 11px; padding: 2px 7px; border-radius: 5px; font-weight: 600;
    background: #1e293b; color: #94a3b8;
  }
  .badge.pending { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
  .badge.posted { background: rgba(16, 185, 129, 0.2); color: #34d399; }
  .badge.polish { background: rgba(168, 85, 247, 0.2); color: #c084fc; }
  .queue-text { font-size: 13.5px; white-space: pre-wrap; word-break: break-word; }
  .queue-sub { font-size: 11.5px; color: var(--muted); margin-top: 4px; }

  .log-list {
    display: flex; flex-direction: column; gap: 8px;
    max-height: 390px; overflow-y: auto; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
  }
  .log-item {
    padding: 9px 11px; border-radius: 8px; background: #090d16; border-left: 3px solid #3b82f6;
  }
  .log-item.success { border-left-color: var(--green); }
  .log-item.warning { border-left-color: var(--amber); }
  .log-item.error { border-left-color: var(--red); }
  .log-time { color: var(--muted); font-size: 11px; }
  .log-details { color: var(--muted); margin-top: 3px; word-break: break-all; }

  .toggle-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 0; border-bottom: 1px solid #1e293b; font-size: 13.5px;
  }
  .toggle-row:last-child { border-bottom: none; }
  details summary { cursor: pointer; font-weight: 600; font-size: 14px; color: #93c5fd; padding: 4px 0; }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <div class="bolt-icon">⚡</div>
      <div>
        <h1>Bolt — Autonomous Facebook Page Agent</h1>
        <div class="subtitle">Push any content every minute or hour + First-Comment Link Dropper + Auto-Responder</div>
      </div>
    </div>
    <div class="status-bar">
      <a href="/download/facebook_agent.py" download="facebook_agent.py" style="text-decoration:none;">
        <button class="purple" type="button">⬇️ Download facebook_agent.py</button>
      </a>
      <span id="modePill" class="pill dry">DRY RUN MODE</span>
      <span id="timerPill" class="pill timer">Next push in: --:--</span>
      <button id="pushNowBtn" class="success" onclick="pushNow()">⚡ Push Next Now</button>
      <button id="toggleDryBtn" class="secondary" onclick="toggleDryRun()">Switch to Live</button>
    </div>
  </header>
  <div id="noticeBanner" style="display:none; padding:12px 16px; border-radius:10px; margin-bottom:18px; font-weight:600; font-size:14px;"></div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Queue Pending</div>
      <div class="stat-value" id="statPending">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Posts Pushed</div>
      <div class="stat-value" id="statPosts">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Comments Replied</div>
      <div class="stat-value" id="statComments">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">DMs Replied</div>
      <div class="stat-value" id="statMessages">0</div>
    </div>
  </div>

  <div class="main-grid">
    <!-- LEFT COLUMN: Add Content + Bulk Generator + Queue -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title">1. Feed Content to Push</div>
          <span style="font-size:12px;color:var(--muted)">Separate multiple posts with <code>---</code> on its own line</span>
        </div>
        <label>Post Text / Content (or rough draft for AI to polish)</label>
        <textarea id="postText" placeholder="Write or paste your post here...&#10;---&#10;Want to queue 10 posts at once? Separate each post with ---"></textarea>

        <div class="row" style="margin-top:8px">
          <div>
            <label>First Comment Auto-Drop (Pro Reach Hack: put links here!)</label>
            <input type="text" id="postFirstComment" placeholder="e.g. Grab the full guide here 👉 https://yoursite.com">
          </div>
          <div>
            <label>How to Push</label>
            <select id="postMode">
              <option value="exact">Exact Text (Post as-is)</option>
              <option value="polish">AI Polish (Claude rewrites in brand voice)</option>
            </select>
          </div>
        </div>

        <div class="row" style="margin-top:6px">
          <div>
            <label>Optional Link URL</label>
            <input type="text" id="postLink" placeholder="https://yourwebsite.com/offer">
          </div>
          <div>
            <label>Optional Image URL</label>
            <input type="text" id="postImage" placeholder="https://example.com/photo.jpg">
          </div>
          <div>
            <label>Optional Video URL (.mp4)</label>
            <input type="text" id="postVideo" placeholder="https://example.com/video.mp4">
          </div>
        </div>

        <div style="margin-top:14px; display:flex; gap:10px; flex-wrap:wrap;">
          <button onclick="addContent(false)">+ Add to Queue</button>
          <button class="success" onclick="addContent(true)">⚡ Add &amp; Push Immediately</button>
        </div>

        <details style="margin-top:16px; border-top:1px solid #1e293b; padding-top:10px;">
          <summary>✨ Or Auto-Generate a Batch of Posts by Topic</summary>
          <div class="row" style="margin-top:8px">
            <div style="flex:2">
              <label>Topic / Niche / Offer</label>
              <input type="text" id="genTopic" placeholder="e.g. Personal finance tips for young professionals">
            </div>
            <div style="flex:0.7">
              <label>How Many</label>
              <input type="number" id="genCount" value="5" min="1" max="20">
            </div>
          </div>
          <div style="margin-top:10px">
            <button class="purple sm" onclick="generateBatch()">✨ Generate &amp; Add to Queue</button>
          </div>
        </details>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">2. Content Queue (<span id="queueCount">0</span> items)</div>
          <div style="display:flex; gap:6px;">
            <button class="secondary sm" onclick="queueAction('reset_all')">Reset All to Pending</button>
            <button class="danger sm" onclick="queueAction('clear_all')">Clear Queue</button>
          </div>
        </div>
        <div id="queueList" class="queue-list"></div>
      </div>
    </div>

    <!-- RIGHT COLUMN: Schedule Controls + Live Activity Log + Settings -->
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title">3. Schedule Timer (Every Minute or Hour)</div>
          <button id="pauseResumeBtn" class="secondary sm" onclick="toggleScheduler()">Pause Timer</button>
        </div>
        <label>Push Interval (Minutes)</label>
        <div class="row">
          <input type="number" id="intervalMinutes" step="any" min="0.25" value="60">
          <button onclick="saveInterval()">Set Timer</button>
        </div>
        <div class="preset-btns">
          <button class="secondary sm" onclick="setPresetMinutes(1)">Every 1 Min</button>
          <button class="secondary sm" onclick="setPresetMinutes(5)">Every 5 Mins</button>
          <button class="secondary sm" onclick="setPresetMinutes(15)">Every 15 Mins</button>
          <button class="secondary sm" onclick="setPresetMinutes(30)">Every 30 Mins</button>
          <button class="secondary sm" onclick="setPresetMinutes(60)">Every 1 Hour</button>
          <button class="secondary sm" onclick="setPresetMinutes(360)">Every 6 Hours</button>
          <button class="secondary sm" onclick="setPresetMinutes(720)">Every 12 Hours</button>
        </div>

        <div style="margin-top:14px">
          <div class="toggle-row">
            <span>🔄 Loop / Recycle Queue when finished</span>
            <input type="checkbox" id="loopQueueToggle" onchange="saveToggles()">
          </div>
          <div class="toggle-row">
            <span>🤖 AI Auto-Starter when queue is empty</span>
            <input type="checkbox" id="aiFallbackToggle" onchange="saveToggles()">
          </div>
          <div class="toggle-row">
            <span>💬 Auto-Poll Page Comments (No Webhook Needed)</span>
            <input type="checkbox" id="pollCommentsToggle" onchange="saveToggles()">
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">4. Live Activity Feed</div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="secondary sm" onclick="pollCommentsNow()">🔍 Check FB Comments Now</button>
            <button class="secondary sm" onclick="simulateEvent('comment')">💬 Test Comment</button>
            <button class="secondary sm" onclick="simulateEvent('message')">📩 Test DM</button>
          </div>
        </div>
        <div class="row" style="margin-bottom:10px;">
          <input type="text" id="simText" value="Hey Little Wings! How do I turn my content into cash?" placeholder="Type a test comment or DM here...">
        </div>
        <div id="logList" class="log-list"></div>
      </div>

      <div class="card">
        <details open>
          <summary>⚙️ Facebook Page &amp; AI Credentials (Auto-Saves to .env)</summary>
          <div style="margin-top:12px">
            <label>Facebook Page ID (optional — auto-detected from token)</label>
            <input type="text" id="cfgPageId" placeholder="e.g. 1049281928391">
            <label>Long-Lived Page Access Token (<span id="tokenStatus">not set</span>)</label>
            <input type="password" id="cfgPageToken" placeholder="Paste PAGE_TOKEN here">
            <label>AI Key (<span id="aiKeyStatus">Built-in Free Brain Active ✓</span> — Optional: paste a FREE Groq <code>gsk_...</code> or Gemini <code>AIza...</code> key)</label>
            <input type="password" id="cfgAiKey" placeholder="Optional: gsk_... (Groq Free) or AIza... (Gemini Free) or sk-ant-...">
            <label>Webhook Verify Token</label>
            <input type="text" id="cfgVerifyToken" placeholder="my-secret-verify-token">
            <label>Agent Brand Voice &amp; Instructions</label>
            <textarea id="cfgInstructions" style="min-height:110px"></textarea>
            <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;">
              <button onclick="saveCredentials()">Save Settings</button>
              <button class="secondary" onclick="testFacebookConnection()">Verify Facebook Token</button>
            </div>
          </div>
        </details>
      </div>
    </div>
  </div>
</div>

<script>
let currentState = null;
let initializedInputs = false;

function fmtSeconds(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return `${h}h ${remM}m ${s}s`;
  }
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

async function fetchState() {
  try {
    const r = await fetch('/api/state');
    const data = await r.json();
    currentState = data;
    renderState(data);
  } catch (e) {
    console.error(e);
  }
}

function renderState(data) {
  const cfg = data.config;
  const modePill = document.getElementById('modePill');
  const toggleDryBtn = document.getElementById('toggleDryBtn');
  if (cfg.dry_run) {
    modePill.className = 'pill dry';
    modePill.textContent = '🧪 DRY RUN (Safe Preview)';
    toggleDryBtn.textContent = 'Go Live on Facebook';
  } else {
    modePill.className = 'pill live';
    modePill.textContent = '🟢 LIVE ON FACEBOOK';
    toggleDryBtn.textContent = 'Switch to Dry Run';
  }

  const timerPill = document.getElementById('timerPill');
  const pauseBtn = document.getElementById('pauseResumeBtn');
  if (cfg.scheduler_enabled) {
    timerPill.textContent = `Next push in: ${fmtSeconds(data.seconds_until_next)} (every ${cfg.interval_minutes}m)`;
    pauseBtn.textContent = '⏸ Pause Timer';
  } else {
    timerPill.textContent = '⏸ Scheduler Paused';
    pauseBtn.textContent = '▶ Resume Timer';
  }

  const pendingCount = data.queue.filter(q => q.status === 'pending').length;
  document.getElementById('statPending').textContent = pendingCount;
  document.getElementById('statPosts').textContent = data.stats.posts_sent;
  document.getElementById('statComments').textContent = data.stats.comments_replied;
  document.getElementById('statMessages').textContent = data.stats.messages_replied;
  document.getElementById('queueCount').textContent = data.queue.length;

  if (!initializedInputs) {
    document.getElementById('intervalMinutes').value = cfg.interval_minutes;
    document.getElementById('loopQueueToggle').checked = cfg.loop_queue;
    document.getElementById('aiFallbackToggle').checked = cfg.ai_fallback;
    document.getElementById('pollCommentsToggle').checked = cfg.poll_comments;
    document.getElementById('cfgPageId').value = cfg.page_id || '';
    document.getElementById('cfgVerifyToken').value = cfg.verify_token || '';
    document.getElementById('cfgInstructions').value = cfg.instructions || '';
    initializedInputs = true;
  }
  document.getElementById('tokenStatus').textContent = cfg.has_page_token ? `configured (${cfg.page_token_preview})` : 'not set';
  document.getElementById('aiKeyStatus').textContent = cfg.has_anthropic_key ? 'Custom AI Key Configured ✓' : 'Built-in Free Brain Active ✓ (No key needed)';

  const qEl = document.getElementById('queueList');
  if (!data.queue.length) {
    qEl.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:12px;">Queue is empty. Paste content above or use the Topic Generator!</div>';
  } else {
    qEl.innerHTML = data.queue.map(item => `
      <div class="queue-item ${item.status}">
        <div style="flex:1">
          <div class="queue-meta">
            <span class="badge ${item.status}">${item.status.toUpperCase()}</span>
            <span class="badge ${item.mode}">${item.mode === 'polish' ? '✨ AI Polish' : '📌 Exact Text'}</span>
            <span style="font-size:11px;color:var(--muted)">Runs: ${item.runs || 0}</span>
          </div>
          <div class="queue-text">${escapeHtml(item.text)}</div>
          ${item.first_comment ? `<div class="queue-sub">💬 1st Comment: ${escapeHtml(item.first_comment)}</div>` : ''}
          ${item.link ? `<div class="queue-sub">🔗 ${escapeHtml(item.link)}</div>` : ''}
          ${item.image_url ? `<div class="queue-sub">🖼️ ${escapeHtml(item.image_url)}</div>` : ''}
          ${item.video_url ? `<div class="queue-sub">🎬 ${escapeHtml(item.video_url)}</div>` : ''}
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0;">
          <button class="success sm" onclick="queueAction('push_now', '${item.id}')">Push Now</button>
          <button class="secondary sm" onclick="queueAction('toggle_status', '${item.id}')">${item.status === 'pending' ? 'Skip' : 'Re-queue'}</button>
          <button class="danger sm" onclick="queueAction('delete', '${item.id}')">✕</button>
        </div>
      </div>
    `).join('');
  }

  const logEl = document.getElementById('logList');
  logEl.innerHTML = data.logs.map(l => `
    <div class="log-item ${l.level}">
      <div><span class="log-time">[${l.time}] [${l.category.toUpperCase()}]</span> ${escapeHtml(l.message)}</div>
      ${l.details ? `<div class="log-details">${escapeHtml(l.details)}</div>` : ''}
    </div>
  `).join('');
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

let noticeTimeout = null;
function showNotice(msg, isError = false) {
  const el = document.getElementById('noticeBanner');
  el.style.display = 'block';
  el.style.background = isError ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)';
  el.style.border = isError ? '1px solid rgba(239, 68, 68, 0.5)' : '1px solid rgba(16, 185, 129, 0.5)';
  el.style.color = isError ? '#fca5a5' : '#6ee7b7';
  el.textContent = msg;
  if (noticeTimeout) clearTimeout(noticeTimeout);
  noticeTimeout = setTimeout(() => { el.style.display = 'none'; }, 5000);
}

async function addContent(pushImmediately) {
  const text = document.getElementById('postText').value.trim();
  if (!text) return showNotice('Please enter some content in the Post Text box first!', true);
  const first_comment = document.getElementById('postFirstComment').value.trim();
  const link = document.getElementById('postLink').value.trim();
  const image_url = document.getElementById('postImage').value.trim();
  const video_url = document.getElementById('postVideo').value.trim();
  const mode = document.getElementById('postMode').value;

  const r = await fetch('/api/queue', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text, first_comment, link, image_url, video_url, mode, bulk: true})
  });
  const res = await r.json();
  if (res.ok) {
    document.getElementById('postText').value = '';
    document.getElementById('postFirstComment').value = '';
    document.getElementById('postLink').value = '';
    document.getElementById('postImage').value = '';
    document.getElementById('postVideo').value = '';
    showNotice(`✅ Added ${res.added} post(s) to the queue!`);
    if (pushImmediately && res.items && res.items.length) {
      await queueAction('push_now', res.items[0].id);
    } else {
      await fetchState();
    }
  }
}

async function generateBatch() {
  const topic = document.getElementById('genTopic').value.trim() || 'Turning content into cash on social media';
  const count = parseInt(document.getElementById('genCount').value, 10) || 5;
  const first_comment = document.getElementById('postFirstComment').value.trim();
  showNotice(`✨ Generating ${count} posts about "${topic}"...`);
  const r = await fetch('/api/queue/generate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({topic, count, first_comment})
  });
  const res = await r.json();
  if (res.ok) {
    document.getElementById('genTopic').value = '';
    showNotice(`✅ Generated and added ${res.added} posts to your queue!`);
    await fetchState();
  }
}

async function browserGraphPost(path, paramsObj, token) {
  const form = new URLSearchParams();
  for (const [k, v] of Object.entries(paramsObj)) {
    if (v !== undefined && v !== null && v !== '') form.append(k, v);
  }
  form.append('access_token', token);
  const r = await fetch(`https://graph.facebook.com/v19.0/${path}`, {
    method: 'POST',
    body: form
  });
  const data = await r.json();
  return { ok: r.ok, status: r.status, data };
}

async function handleBrowserFallbackPublish(res) {
  if (!res || !res.fb_result || !res.fb_result.browser_fallback) return;
  const cfg = currentState && currentState.config ? currentState.config : {};
  const token = cfg.page_token;
  if (!token) {
    showNotice('❌ Missing PAGE_TOKEN! Paste your Facebook Page Token in Settings below.', true);
    return;
  }
  const fbRes = await browserGraphPost(res.fb_result.path, res.fb_result.data, token);
  if (fbRes.ok) {
    const postId = fbRes.data.post_id || fbRes.data.id;
    await fetch('/api/log-client', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        level: 'success',
        category: 'facebook',
        message: `Published LIVE to Facebook /${res.fb_result.path} (ID: ${postId})`,
        details: JSON.stringify(fbRes.data)
      })
    });
    if (res.item && res.item.first_comment && postId) {
      const cRes = await browserGraphPost(`${postId}/comments`, {message: res.item.first_comment}, token);
      if (cRes.ok) {
        await fetch('/api/log-client', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            level: 'success',
            category: 'facebook',
            message: `Auto-dropped First Comment on post ${postId}`
          })
        });
      }
    }
    showNotice(`🎉 Published LIVE to your Facebook Page! (Post ID: ${postId})`);
  } else {
    const errMsg = (fbRes.data && fbRes.data.error && fbRes.data.error.message) || JSON.stringify(fbRes.data);
    await fetch('/api/log-client', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        level: 'error',
        category: 'facebook',
        message: `Facebook API error on /${res.fb_result.path}`,
        details: errMsg
      })
    });
    showNotice(`❌ Facebook error: ${errMsg}`, true);
  }
}

async function pushNow() {
  const r = await fetch('/api/queue/action', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action: 'push_now'})
  });
  const res = await r.json();
  if (res.ok) {
    await fetchState();
    if (res.fb_result && res.fb_result.browser_fallback) {
      await handleBrowserFallbackPublish(res);
    } else {
      showNotice('⚡ Pushed post! Check the Live Activity Feed below.');
    }
  } else {
    showNotice(res.reason || 'Queue has no pending items.', true);
  }
  await fetchState();
}

async function queueAction(action, id = null) {
  const r = await fetch('/api/queue/action', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action, id})
  });
  const res = await r.json();
  if (action === 'push_now' && res && res.fb_result && res.fb_result.browser_fallback) {
    await fetchState();
    await handleBrowserFallbackPublish(res);
  }
  await fetchState();
}

async function setPresetMinutes(mins) {
  document.getElementById('intervalMinutes').value = mins;
  await saveInterval();
}

async function saveInterval() {
  const interval_minutes = parseFloat(document.getElementById('intervalMinutes').value) || 60;
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({interval_minutes})
  });
  showNotice(`⏱️ Timer set to push every ${interval_minutes} minute(s)!`);
  await fetchState();
}

async function saveToggles() {
  const loop_queue = document.getElementById('loopQueueToggle').checked;
  const ai_fallback = document.getElementById('aiFallbackToggle').checked;
  const poll_comments = document.getElementById('pollCommentsToggle').checked;
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({loop_queue, ai_fallback, poll_comments})
  });
  showNotice('✅ Updated schedule preferences!');
  await fetchState();
}

async function toggleDryRun() {
  if (!currentState) return;
  const nextDry = !currentState.config.dry_run;
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({dry_run: nextDry})
  });
  showNotice(nextDry ? '🧪 Switched to Safe Dry Run Mode.' : '🟢 Switched to LIVE Facebook Mode!');
  await fetchState();
}

async function toggleScheduler() {
  if (!currentState) return;
  const nextEnabled = !currentState.config.scheduler_enabled;
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scheduler_enabled: nextEnabled})
  });
  showNotice(nextEnabled ? '▶ Timer resumed!' : '⏸ Timer paused.');
  await fetchState();
}

async function saveCredentials() {
  const payload = {
    page_id: document.getElementById('cfgPageId').value,
    page_token: document.getElementById('cfgPageToken').value,
    anthropic_api_key: document.getElementById('cfgAiKey').value,
    verify_token: document.getElementById('cfgVerifyToken').value,
    instructions: document.getElementById('cfgInstructions').value,
  };
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  document.getElementById('cfgPageToken').value = '';
  document.getElementById('cfgAiKey').value = '';
  showNotice('✅ Saved Settings & Brand Instructions!');
  await fetchState();
}

async function testFacebookConnection() {
  await saveCredentials();
  await fetchState();
  showNotice('🔍 Checking Facebook Page token...');
  const token = currentState && currentState.config ? currentState.config.page_token : '';
  const pageId = (currentState && currentState.config && currentState.config.page_id) || 'me';
  if (!token) {
    return showNotice('❌ Paste your Long-Lived Page Access Token first!', true);
  }
  try {
    const r = await fetch(`https://graph.facebook.com/v19.0/${pageId}?fields=id,name&access_token=${encodeURIComponent(token)}`);
    const data = await r.json();
    if (r.ok && data.name) {
      document.getElementById('cfgPageId').value = data.id || '';
      await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({page_id: data.id})
      });
      await fetch('/api/log-client', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          level: 'success',
          category: 'facebook',
          message: `Connected to Facebook Page: ${data.name} (ID: ${data.id})`
        })
      });
      showNotice(`✅ Connected to Facebook Page: ${data.name} (ID: ${data.id})`);
    } else {
      const errMsg = (data.error && data.error.message) || JSON.stringify(data);
      showNotice(`❌ Facebook token error: ${errMsg}`, true);
    }
  } catch (err) {
    const r = await fetch('/api/test-fb', {method: 'POST'});
    const data = await r.json();
    if (data.ok) {
      showNotice(`✅ Connected to Facebook Page: ${data.page.name} (ID: ${data.page.id})`);
    } else {
      showNotice(`❌ Facebook check failed: ${data.error}`, true);
    }
  }
  await fetchState();
}

async function pollCommentsNow() {
  await fetchState();
  const cfg = currentState && currentState.config ? currentState.config : {};
  const token = cfg.page_token;
  const pageId = cfg.page_id || 'me';
  if (!token) {
    return showNotice('⚠️ Paste your Facebook Page Token in Settings below first to check real Facebook comments!', true);
  }
  showNotice('🔍 Scanning your Facebook Page for new comments...');
  try {
    const url = `https://graph.facebook.com/v19.0/${pageId}/posts?fields=id,message,comments.limit(10){id,from,message,created_time}&limit=5&access_token=${encodeURIComponent(token)}`;
    const r = await fetch(url);
    const data = await r.json();
    if (!r.ok) {
      const errMsg = (data.error && data.error.message) || JSON.stringify(data);
      return showNotice(`❌ Facebook error: ${errMsg}`, true);
    }
    const seen = new Set((currentState && currentState.seen_ids) || []);
    let newCount = 0;
    for (const post of (data.data || [])) {
      const comments = (post.comments && post.comments.data) || [];
      for (const c of comments) {
        if (!c.id || seen.has(c.id)) continue;
        if (c.from && c.from.id && c.from.id === cfg.page_id) continue;
        newCount++;
        const authorName = (c.from && c.from.name) || 'friend';
        const brainRes = await fetch('/api/brain-reply', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            comment_id: c.id,
            author: authorName,
            text: c.message || '',
            post_message: post.message || ''
          })
        });
        const brainData = await brainRes.json();
        const decision = (brainData && brainData.decision) || {};
        if (decision.action === 'reply' && decision.text) {
          if (cfg.dry_run) {
            await fetch('/api/log-client', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                level: 'info',
                category: 'comment',
                seen_id: c.id,
                stat_inc: 'comments_replied',
                message: `[DRY RUN] Would reply to ${authorName}'s comment ("${c.message}"): "${decision.text}"`
              })
            });
          } else {
            const rep = await browserGraphPost(`${c.id}/comments`, {message: decision.text}, token);
            if (rep.ok) {
              await fetch('/api/log-client', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                  level: 'success',
                  category: 'comment',
                  seen_id: c.id,
                  stat_inc: 'comments_replied',
                  message: `Replied LIVE to ${authorName}: "${decision.text}"`
                })
              });
            }
          }
        }
      }
    }
    showNotice(`✅ Checked Facebook Page comments (${newCount} new comment(s) processed).`);
  } catch (e) {
    showNotice(`❌ Error checking comments: ${e.message}`, true);
  }
  await fetchState();
}

async function simulateEvent(kind) {
  const text = document.getElementById('simText').value.trim() || 'Hey Little Wings! How do I turn my content into cash?';
  await fetch('/api/simulate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({kind, author: 'Sarah', text})
  });
  showNotice(`✅ Simulated incoming ${kind}! See Bolt's reply in the Live Activity Feed below.`);
  await fetchState();
}

let isPushingAuto = false;
fetchState();
setInterval(async () => {
  await fetchState();
  if (currentState && currentState.config && currentState.config.scheduler_enabled && currentState.seconds_until_next <= 1 && !isPushingAuto) {
    isPushingAuto = true;
    try {
      await pushNow();
    } finally {
      setTimeout(() => { isPushingAuto = false; }, 3000);
    }
  }
}, 1000);

// Auto-poll Facebook Page comments from the browser every 30s when a Page Token is set
setInterval(async () => {
  if (currentState && currentState.config && currentState.config.poll_comments && currentState.config.has_page_token) {
    try {
      await pollCommentsNow();
    } catch (e) {}
  }
}, 30000);
</script>
</body>
</html>
"""


@app.get("/")
def home():
    return Response(DASHBOARD_HTML, mimetype="text/html")


@app.get("/download/facebook_agent.py")
def download_script():
    with open(__file__, "r", encoding="utf-8") as f:
        code = f.read()
    return Response(
        code,
        mimetype="text/x-python",
        headers={"Content-Disposition": 'attachment; filename="facebook_agent.py"'},
    )


def parse_cli():
    parser = argparse.ArgumentParser(description="Bolt — Autonomous Facebook Page Agent & Content Pusher")
    parser.add_argument("--every", type=float, default=None, help="Push interval in minutes (e.g. --every 1 or --every 60)")
    parser.add_argument("--live", action="store_true", help="Disable DRY_RUN and publish live to Facebook")
    parser.add_argument("--push", type=str, default=None, help="Push a single post immediately and exit")
    parser.add_argument("--add", type=str, default=None, help="Add a post to the persistent queue and exit")
    parser.add_argument("--link", type=str, default="", help="Optional link URL for --push or --add")
    parser.add_argument("--image", type=str, default="", help="Optional image URL for --push or --add")
    parser.add_argument("--video", type=str, default="", help="Optional video URL for --push or --add")
    parser.add_argument("--first-comment", type=str, default="", help="Optional first comment to auto-drop under the post")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cli()
    load_state()

    if args.every is not None:
        state["config"]["interval_minutes"] = max(0.25, float(args.every))
        state["next_run_ts"] = time.time() + (state["config"]["interval_minutes"] * 60.0)
    if args.live:
        state["config"]["dry_run"] = False

    if args.add:
        item = {
            "id": str(uuid.uuid4())[:8],
            "text": args.add.strip(),
            "link": args.link.strip(),
            "image_url": args.image.strip(),
            "video_url": args.video.strip(),
            "first_comment": args.first_comment.strip(),
            "mode": "exact",
            "status": "pending",
            "runs": 0,
            "last_posted": None,
        }
        state["queue"].append(item)
        save_state()
        print(f"Added item #{item['id']} to queue ({len(state['queue'])} total).")
        sys.exit(0)

    if args.push:
        res = publish_content_item(
            text=args.push.strip(),
            link=args.link.strip(),
            image_url=args.image.strip(),
            video_url=args.video.strip(),
            first_comment=args.first_comment.strip(),
        )
        save_state()
        print("Push result:", json.dumps(res, indent=2))
        sys.exit(0)

    add_log(
        "info",
        "system",
        f"Bolt Agent starting. DRY_RUN={state['config']['dry_run']} | Interval={state['config']['interval_minutes']} min",
    )
    threading.Thread(target=background_worker_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    url = f"http://localhost:{port}"
    print(f"\n⚡ Bolt Control Panel running! Ctrl+Click to open: {url}\n")
    try:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
    app.run(host="0.0.0.0", port=port)
