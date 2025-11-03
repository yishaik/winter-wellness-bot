# Winter Wellness Telegram Bot (Raspberry Pi)

[![CI](https://github.com/yishaik/winter-wellness-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/yishaik/winter-wellness-bot/actions/workflows/ci.yml)

בוט טלגרם שמסייע להתמודדות עם דכדוך חורף:
- תזכורות יומיות בשעה **09:00** ו-**21:00** (אזור זמן Asia/Jerusalem)
- תחזית מזג אוויר (Open-Meteo, ללא צורך ב־API key)
- אינטגרציה עם נתוני הסאונה שלך (SQLite קיים או HTTP `/history`)
- בדיקת מצב רוח קצרה ושמירה ל־CSV

## התקנה מהירה (Raspberry Pi)
יש שתי אפשרויות: התקנה אוטומטית עם סקריפט, או התקנה ידנית.

### א) התקנה אוטומטית (מומלץ)
הרץ כ־root (או `sudo`) במחשב היעד:
```bash
curl -fsSL -o install_pi.sh https://raw.githubusercontent.com/yishaik/winter-wellness-bot/main/scripts/install_pi.sh
sudo bash install_pi.sh
```
או מתוך הספרייה של הפרויקט שכבר הועתקה ל־Pi:
```bash
cd /path/to/repo
sudo scripts/install_pi.sh
```
הסקריפט:
- יוצר משתמש `wellness` ושתי תיקיות `/opt/winter_wellness_bot` ו־`/var/lib/winter_wellness_bot`
- מעתיק את הקוד, מתקין venv ותלויות
- שואל אותך על משתני הסביבה וכותב קובץ `.env`
- יוצר ומפעיל שירות `systemd` בשם `winter-wellness.service`

לאחר ההתקנה ניתן לשנות ערכים ב־`/opt/winter_wellness_bot/.env` ואז להריץ `sudo systemctl restart winter-wellness.service`.

### ב) התקנה ידנית
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv
sudo useradd -r -s /usr/sbin/nologin wellness || true
sudo mkdir -p /opt/winter_wellness_bot /var/lib/winter_wellness_bot
sudo chown -R wellness:wellness /opt/winter_wellness_bot /var/lib/winter_wellness_bot
cd /opt/winter_wellness_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# ערוך את .env ושבץ את ה-TOKEN וה-CHAT_ID שלך
# הערה: הקוד טוען קובץ .env אוטומטית (python-dotenv)
```

## הרצה ידנית
```bash
source /opt/winter_wellness_bot/.venv/bin/activate
python main.py
```

## בדיקות (Tests)
להרצת בדיקות יחידה מקומית:
```bash
pip install -r requirements-dev.txt
pytest -q
```

## ממשק ניהול WebUI (עריכת הגדרות, סטטוס ושליטה בשירות)
נוסף ממשק ניהול פשוט ב־Flask תחת `webui/` המאפשר:
- עריכת קובץ `.env` (טוקן/צ׳אט/תזמונים/מקור סאונה וכו')
- צפייה בסטטוס השירות (`systemctl status` + `journalctl`)
- שליטה בשירות: start/stop/restart/enable/disable

הרצה:
```bash
source /opt/winter_wellness_bot/.venv/bin/activate
pip install -r requirements.txt

# ברירת מחדל מנהלת את /opt/winter_wellness_bot ואת השירות winter-wellness.service
python webui/app.py

# ניתן להתאים תיקייה ושם שירות דרך משתני סביבה:
# MANAGED_DIR=/opt/winter_wellness_bot SERVICE_NAME=winter-wellness.service PORT=8080 python webui/app.py
```
הערות:
- כדי שהכפתורים יעבדו (systemctl), יש להריץ את ה־WebUI עם הרשאות מתאימות (root) או להגדיר כללי sudo/polkit המאפשרים שליטה בשירות.
- ה־WebUI נועד לרוץ ברשת פרטית מאובטחת (ללא אימות). במידת הצורך אפשר להוסיף אימות בסיסי ב־reverse proxy או להרחיב את הקוד.

## הפעלה כ־systemd Service
צור קובץ `/etc/systemd/system/winter-wellness.service` עם התוכן הבא:
```
[Unit]
Description=Winter Wellness Telegram Bot
After=network-online.target

[Service]
Type=simple
User=wellness
WorkingDirectory=/opt/winter_wellness_bot
EnvironmentFile=/opt/winter_wellness_bot/.env
ExecStart=/opt/winter_wellness_bot/.venv/bin/python /opt/winter_wellness_bot/main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
לאחר מכן:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now winter-wellness.service
sudo systemctl status winter-wellness.service
```

## CI
התצורה כוללת GitHub Actions (`.github/workflows/ci.yml`) שמריץ בדיקות על Python 3.11 בכל push/PR.

## הגדרות סביבה (.env)
ראה `.env.example`. חשוב להגדיר:
- `TELEGRAM_BOT_TOKEN`: טוקן הבוט
- `TELEGRAM_CHAT_ID`: ה־chat id שלך (למשל מה־@userinfobot בטלגרם)

חלופה ל־`TELEGRAM_CHAT_ID`: אם לא הוגדר, ניתן לשלוח `/start` בצ׳אט פרטי עם הבוט
וה־chat id יישמר אוטומטית לקובץ `DATA_DIR/chat_id.txt` לטובת שליחה מתוזמנת.

**מקור נתוני סאונה**:  
בחר אחד:
- `SAUNA_SQLITE_PATH=/var/lib/sauna/sauna.db` (או הנתיב בו נמצאת הטבלה `temperatures`)  
  - נתמך: עמודות `ts` (epoch seconds) + `temperature` **או** `timestamp` (ISO) + `celsius`
- `SAUNA_BASE_URL=http://127.0.0.1:5000` (שרת עם `/history?from=&to=` המחזיר JSON)

התגליות (sessions) מוגדרות כברירת מחדל: טמפ׳ ≥45°C למשך ≥10 דקות, עם מרווח נפילה עד 8 דק׳.

## הערות הפעלה
- הקוד יוצר את הספרייה ב־`DATA_DIR` (ברירת מחדל: `.`) אם אינה קיימת, עבור לוגים/מצב.
- אם `TELEGRAM_CHAT_ID` לא הוגדר וגם לא בוצע `/start`, שליחה מתוזמנת תידחה עם הודעת אזהרה בלוג.

## משתני סביבה נוספים
- `LOG_LEVEL` — רמת לוג (ברירת מחדל `INFO`; אפשר `DEBUG`/`WARNING`/`ERROR`).
- `LOG_TO_FILE` — אם `1/true`, כותב לוג לקובץ `DATA_DIR/bot.log`.
- `MORNING_TIME` — שעת שליחה בוקר בפורמט `HH:MM` (ברירת מחדל `09:00`).
- `EVENING_TIME` — שעת שליחה ערב בפורמט `HH:MM` (ברירת מחדל `21:00`).
- `DISABLE_MORNING` — אם `1/true`, מבטל שליחת בוקר.
- `DISABLE_EVENING` — אם `1/true`, מבטל שליחת ערב.
- `MOOD_LOG_MAX_BYTES` — הגבלת גודל לקובץ מצב רוח (ברוטציה אוטומטית), אופציונלי.

בנוסף, הקוד מנסה מספר ניסיונות בקריאת היסטוריית סאונה דרך HTTP עם backoff, ומוודא קלטים.

## פקודות בטלגרם
- `/start` — הפעלה וקבלת כפתורים
- `/now` — שליחת דוח מיידי (מזג אוויר + סאונה + טיפים)
- `/sauna` — היסטוריית סשנים אחרונים (48 שעות)
- `/mood` — דירוג מצב רוח 1–5 (נשמר ל־CSV)
- `/help` — עזרה קצרה והסבר על התזמון

הערה: כרגע המודל הוא של מנוי יחיד (single subscriber). אם `TELEGRAM_CHAT_ID` ריק, שלח `/start` בצ׳אט פרטי והמערכת תשמור את ה־chat id לשימוש עתידי.

## הערות
- אם תרצה שליחת גרפים/תמונות — ניתן להוסיף בהמשך.
- אם תרצה הודעות חכמות לפי תחזית גשם/קור — אפשרי להרחיב בקלות (יש כבר Open‑Meteo).
