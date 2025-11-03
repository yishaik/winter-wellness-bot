#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Winter Wellness Telegram Bot (Raspberry Pi)
- Twice-daily reminders (09:00, 21:00 Asia/Jerusalem)
- Weather forecast via Open-Meteo
- Sauna session inference from existing SQLite DB or HTTP API (/history)
- Simple mood check-in
"""

import os
import sys
import time
import json
import math
import queue
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import requests
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# --- Optional .env loading ---
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# --- Config via env ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()  # optional: fixed chat id, else /start needed
TIMEZONE = os.getenv("TZ", "Asia/Jerusalem")
LAT = float(os.getenv("LAT", "32.0853"))   # Tel Aviv default
LON = float(os.getenv("LON", "34.7818"))
SAUNA_SQLITE_PATH = os.getenv("SAUNA_SQLITE_PATH", "").strip()
SAUNA_BASE_URL = os.getenv("SAUNA_BASE_URL", "").strip().rstrip("/")
SAUNA_TEMP_THRESHOLD_C = float(os.getenv("SAUNA_TEMP_THRESHOLD_C", "45.0"))
SAUNA_MIN_DURATION_MIN = int(os.getenv("SAUNA_MIN_DURATION_MIN", "10"))
DATA_DIR = os.getenv("DATA_DIR", ".")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper().strip()
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "0").lower().strip() in {"1", "true", "yes", "on"}
MORNING_TIME = os.getenv("MORNING_TIME", "09:00").strip()
EVENING_TIME = os.getenv("EVENING_TIME", "21:00").strip()
DISABLE_MORNING = os.getenv("DISABLE_MORNING", "0").lower().strip() in {"1", "true", "yes", "on"}
DISABLE_EVENING = os.getenv("DISABLE_EVENING", "0").lower().strip() in {"1", "true", "yes", "on"}

# Logging
FMT = "%(asctime)s %(levelname)s %(name)s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"
log = logging.getLogger("winter_wellness")
try:
    level = getattr(logging, LOG_LEVEL, logging.INFO)
except Exception:
    level = logging.INFO
log.setLevel(level)
if not log.handlers:
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(FMT, datefmt=DATEFMT))
    log.addHandler(sh)

# Ensure data directory exists for logs/persistence
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    pass
if LOG_TO_FILE:
    try:
        fh = logging.FileHandler(os.path.join(DATA_DIR, "bot.log"))
        fh.setFormatter(logging.Formatter(FMT, datefmt=DATEFMT))
        fh.setLevel(level)
        log.addHandler(fh)
        log.info("File logging enabled at %s", os.path.join(DATA_DIR, "bot.log"))
    except Exception as e:
        log.warning(f"Failed to enable file logging: {e}")

# Validate token
if not BOT_TOKEN:
    log.error("Missing TELEGRAM_BOT_TOKEN in environment")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# --- Helpers ---
def local_now():
    # naive offset handling by environment TZ — APScheduler handles tz; for stamping use local time
    return datetime.now()

def bold(s: str) -> str:
    return f"<b>{s}</b>"

try:
    from .utils import human_duration, infer_sessions  # package-style import
except Exception:
    from utils import human_duration, infer_sessions  # script-style fallback

def fetch_open_meteo(lat: float, lon: float):
    # Today + tonight simple forecast
    # https://api.open-meteo.com/v1/forecast?latitude=32.0853&longitude=34.7818&hourly=temperature_2m,relative_humidity_2m,precipitation,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=auto
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,precipitation,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": TIMEZONE,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Open-Meteo error: {e}")
        return None

def summarize_weather(data: dict) -> str:
    if not data:
        return "⛅️ תחזית לא זמינה כרגע."
    try:
        d = data["daily"]
        tmax = d["temperature_2m_max"][0]
        tmin = d["temperature_2m_min"][0]
        return f"⛅️ היום: מקס׳ {round(tmax)}°C · מינ׳ {round(tmin)}°C"
    except Exception:
        return "⛅️ תחזית לא זמינה כרגע."

def fetch_sauna_history_from_sqlite(path: str, start_ts: datetime, end_ts: datetime):
    # Expect a table with at least: timestamp (ISO or unix), temperature (C)
    rows = []
    if not os.path.exists(path):
        return rows
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Try common schemas: timestamps either epoch seconds in 'ts' or ISO string in 'timestamp'
        # We'll attempt both.
        # 1) epoch seconds in 'ts' column
        try:
            cur.execute("SELECT ts, temperature FROM temperatures WHERE ts BETWEEN ? AND ? ORDER BY ts ASC",
                        (int(start_ts.timestamp()), int(end_ts.timestamp())))
            rows = [(datetime.fromtimestamp(r["ts"]), float(r["temperature"])) for r in cur.fetchall()]
            if rows:
                return rows
        except Exception:
            pass
        # 2) ISO string in 'timestamp' column
        try:
            cur.execute("SELECT timestamp, celsius FROM temperatures WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp ASC",
                        (start_ts.isoformat(), end_ts.isoformat()))
            rows = [(datetime.fromisoformat(r["timestamp"]), float(r["celsius"])) for r in cur.fetchall()]
            return rows
        except Exception:
            return []
    except Exception as e:
        log.warning(f"SQLite read error: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

def fetch_sauna_history_from_http(base_url: str, start_ts: datetime, end_ts: datetime):
    # Expect server exposing /history?from=ISO&to=ISO -> list of {timestamp, celsius}
    url = f"{base_url}/history"
    params = {"from": start_ts.isoformat(), "to": end_ts.isoformat()}
    attempts = 3
    backoff = 2
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                log.warning("HTTP history: unexpected payload (not a list)")
                return []
            rows = []
            limit = 10000
            for idx, item in enumerate(data):
                if idx >= limit:
                    log.warning("HTTP history truncated at %d items", limit)
                    break
                if not isinstance(item, dict):
                    continue
                ts = item.get("timestamp") or item.get("time") or item.get("ts")
                temp = item.get("celsius") or item.get("temp") or item.get("temperature")
                if ts is None or temp is None:
                    continue
                try:
                    t = datetime.fromisoformat(str(ts))
                except Exception:
                    try:
                        t = datetime.fromtimestamp(float(ts))
                    except Exception:
                        continue
                try:
                    tempf = float(temp)
                except Exception:
                    continue
                rows.append((t, tempf))
            rows.sort(key=lambda x: x[0])
            return rows
        except Exception as e:
            if i < attempts - 1:
                sleep_s = backoff ** i
                log.warning(f"HTTP history error (attempt {i+1}/{attempts}): {e}, retrying in {sleep_s}s")
                try:
                    time.sleep(sleep_s)
                except Exception:
                    pass
            else:
                log.warning(f"HTTP history error: {e}")
    return []

 # infer_sessions provided by utils

async def build_daily_message(prefix_emoji: str) -> str:
    # Weather
    wx = fetch_open_meteo(LAT, LON)
    wx_summary = summarize_weather(wx)

    # Sauna sessions in last 24h
    now = local_now()
    start = now - timedelta(hours=24)
    samples = []
    if SAUNA_SQLITE_PATH:
        log.debug("Fetching sauna history from SQLite")
        samples = fetch_sauna_history_from_sqlite(SAUNA_SQLITE_PATH, start, now)
    if not samples and SAUNA_BASE_URL:
        log.debug("Fetching sauna history from HTTP base URL")
        samples = fetch_sauna_history_from_http(SAUNA_BASE_URL, start, now)

    sessions = infer_sessions(
        samples,
        threshold_c=SAUNA_TEMP_THRESHOLD_C,
        min_duration_min=SAUNA_MIN_DURATION_MIN,
    )

    sauna_part = "🧖‍♂️ אין סשן סאונה ב‑24 השעות האחרונות."
    if sessions:
        last = sessions[-1]
        sauna_part = (
            f"🧖‍♂️ סשן אחרון: {last['start'].strftime('%d.%m %H:%M')} · "
            f"{human_duration(last['minutes'])} · מקס׳ {round(last['max_c'])}°C"
        )

    tips = [
        "לך/י ל‑20 דק׳ אור בוקר 🌤️",
        "10 דק׳ נשימה/מדיטציה",
        "תנועה קצרה: הליכה או מתיחות",
        "שתיית מים + ארוחה קלה",
    ]
    tip = "• " + " · ".join(tips)

    msg = (
        f"{prefix_emoji} {bold('בדיקת חורף יומית')}\n"
        f"{wx_summary}\n"
        f"{sauna_part}\n"
        f"{tip}\n"
        f"—\n"
        f"פקודות: /now · /sauna · /mood"
    )
    return msg

# --- Commands ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/now"), KeyboardButton(text="/sauna")],
                  [KeyboardButton(text="/mood")]],
        resize_keyboard=True
    )
    # Persist chat id for scheduled messages, if not provided via env
    try:
        chat_id_path = os.path.join(DATA_DIR, "chat_id.txt")
        with open(chat_id_path, "w", encoding="utf-8") as f:
            f.write(str(message.chat.id))
        log.info(f"Persisted chat id to {chat_id_path}: {message.chat.id}")
    except Exception as e:
        log.warning(f"Could not persist chat id: {e}")

    await message.answer(
        "הבוט מוכן. אשלח תזכורות ב‑09:00 ו‑21:00.\n"
        "פקודות זמינות: /now /sauna /mood",
        reply_markup=kb
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "פקודות:\n"
        "/start — התחלה וקבלת כפתורים\n"
        "/now — דוח מיידי (מזג אוויר + סאונה + טיפים)\n"
        "/sauna — סשנים אחרונים\n"
        "/mood — דירוג מצב רוח 1–5\n"
        "—\n"
        "תזמון ניתן להגדרה ע""י MORNING_TIME ו‑EVENING_TIME (HH:MM).\n"
        "ניתן להשבית עם DISABLE_MORNING=1 או DISABLE_EVENING=1."
    )
    await message.answer(text)

@dp.message(Command("now"))
async def cmd_now(message: types.Message):
    msg = await build_daily_message("🔔")
    await message.answer(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@dp.message(Command("sauna"))
async def cmd_sauna(message: types.Message):
    now = local_now()
    start = now - timedelta(hours=48)
    samples = []
    if SAUNA_SQLITE_PATH:
        samples = fetch_sauna_history_from_sqlite(SAUNA_SQLITE_PATH, start, now)
    if not samples and SAUNA_BASE_URL:
        samples = fetch_sauna_history_from_http(SAUNA_BASE_URL, start, now)

    sessions = infer_sessions(samples, threshold_c=SAUNA_TEMP_THRESHOLD_C, min_duration_min=SAUNA_MIN_DURATION_MIN)

    if not sessions:
        await message.answer("🧖‍♂️ לא נמצאו סשנים ב‑48 השעות האחרונות.", disable_web_page_preview=True)
        return

    lines = []
    for s in sessions[-5:]:
        lines.append(f"{s['start'].strftime('%d.%m %H:%M')} · {human_duration(s['minutes'])} · מקס׳ {round(s['max_c'])}°C")
    await message.answer("🧖‍♂️ סשני סאונה אחרונים:\n" + "\n".join(lines))

@dp.message(Command("mood"))
async def cmd_mood(message: types.Message):
    # Simple quick check-in via buttons 1-5
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Mood 1️⃣"), KeyboardButton(text="Mood 2️⃣"), KeyboardButton(text="Mood 3️⃣")],
                  [KeyboardButton(text="Mood 4️⃣"), KeyboardButton(text="Mood 5️⃣")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("איך המצב עכשיו? (1 נמוך · 5 גבוה)", reply_markup=kb)

@dp.message()
async def handle_mood_buttons(message: types.Message):
    if message.text and message.text.startswith("Mood "):
        try:
            score = int(message.text.split()[1][0])
        except Exception:
            score = None
        if score is None or score < 1 or score > 5:
            await message.answer("נא לבחור מ‑1 עד 5.")
            return
        # Append to local CSV for simplicity
        log_dir = os.getenv("DATA_DIR", ".")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "mood_log.csv")
        # Rotate file if exceeds configured size
        try:
            max_bytes = int(os.getenv("MOOD_LOG_MAX_BYTES", "0"))
        except Exception:
            max_bytes = 0
        if max_bytes > 0 and os.path.exists(path):
            try:
                if os.path.getsize(path) >= max_bytes:
                    ts = datetime.now().strftime("%Y%m%d%H%M%S")
                    new_name = os.path.join(log_dir, f"mood_log-{ts}.csv")
                    os.replace(path, new_name)
                    log.info("Rotated mood log to %s", new_name)
            except Exception as e:
                log.warning(f"Failed to rotate mood log: {e}")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()},{score}\n")
        await message.answer(f"תודה! נשמר דירוג מצב רוח: {score}")

async def send_scheduled(prefix_emoji: str):
    msg = await build_daily_message(prefix_emoji)
    # choose chat_id: fixed CHAT_ID or broadcast to recent /start? Using fixed for simplicity.
    target = CHAT_ID
    # Fallback to persisted chat id if env not set
    if not target:
        try:
            chat_id_path = os.path.join(DATA_DIR, "chat_id.txt")
            if os.path.exists(chat_id_path):
                with open(chat_id_path, "r", encoding="utf-8") as f:
                    target = f.read().strip()
        except Exception as e:
            log.warning(f"Failed reading persisted chat id: {e}")
    if not target:
        log.warning("CHAT_ID not set and no persisted chat id found; skipping scheduled send.")
        return
    try:
        await bot.send_message(chat_id=target, text=msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        log.error(f"Failed to send scheduled message: {e}")

def _parse_hhmm(s: str):
    try:
        parts = s.split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0])
        m = int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return h, m
    except Exception:
        return None

async def main():
    # Schedules based on MORNING_TIME / EVENING_TIME (HH:MM) and disable flags
    morning = _parse_hhmm(MORNING_TIME)
    evening = _parse_hhmm(EVENING_TIME)
    if not DISABLE_MORNING and morning:
        scheduler.add_job(send_scheduled, CronTrigger(hour=morning[0], minute=morning[1]), args=["🌤️"])
        log.info("Morning schedule set for %02d:%02d", morning[0], morning[1])
    else:
        log.info("Morning schedule disabled or invalid time")
    if not DISABLE_EVENING and evening:
        scheduler.add_job(send_scheduled, CronTrigger(hour=evening[0], minute=evening[1]), args=["🌙"])
        log.info("Evening schedule set for %02d:%02d", evening[0], evening[1])
    else:
        log.info("Evening schedule disabled or invalid time")
    scheduler.start()
    log.info("Scheduler started")

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped.")
