# Winter Wellness Bot

Telegram bot and simple WebUI to help with winter wellness routines on a Raspberry Pi.

- Twice-daily reminders (morning/evening)
- Weather via Open‑Meteo
- Sauna session detection (SQLite or HTTP history)
- Quick mood check-in persisted to CSV
- Flask-based admin WebUI to edit `.env` and control the systemd service

Quick start and full docs live under `winter_wellness_bot/README.md`.

Useful links:
- Install script (raw): https://raw.githubusercontent.com/yishaik/winter-wellness-bot/main/scripts/install_pi.sh
- CI: GitHub Actions workflow at `.github/workflows/ci.yml`
