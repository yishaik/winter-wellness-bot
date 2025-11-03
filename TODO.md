# Winter Wellness Bot – TODO

This document tracks tasks by category, and whether they are agent-completable or require a human.

Legend:
- [x] Done
- [ ] Pending
- Agent: can be completed by me (the agent)
- Human: requires human access/decisions/hardware/secrets

## Project Setup & Docs
- [x] Add `.gitignore` for venv, env, caches, data files — Agent
- [x] Document dotenv auto-loading and chat id fallback — Agent
- [ ] Polish README with screenshots and example messages — Human

## Configuration & Env
- [x] Load `.env` automatically via `python-dotenv` (optional) — Agent
- [x] Ensure `DATA_DIR` is created on startup — Agent
- [ ] Provide sample `.env` for multiple environments (dev/prod) — Human

## Bot Functionality
- [x] Persist chat id on `/start` to `DATA_DIR/chat_id.txt` and use as fallback for scheduled sends — Agent
- [ ] Support multiple subscribers (not just a single chat id) — Agent/Human (needs product decision)
- [x] Add `/help` command with concise guidance — Agent
- [ ] Add richer tips logic (e.g., weather-aware) — Agent (optional)

## Sauna Data Integration
- [ ] Add unit tests for session inference edge-cases — Agent
- [ ] Make SQLite schema detection configurable (table/column names) — Agent
- [x] Add retry/backoff for HTTP history source — Agent
- [x] Validate inputs from HTTP sauna source — Agent
- [ ] Human validation against real sauna dataset — Human

## Scheduling & Timezone
- [x] Expose schedule times via env (`MORNING_TIME`, `EVENING_TIME`) — Agent
- [x] Option to disable one of the two schedules — Agent
- [ ] Human confirmation of local timezone correctness on target Pi — Human

## Persistence & Storage
- [x] Mood CSV written under `DATA_DIR` — Agent (existing)
- [x] Rotate/limit mood CSV (size or date-based rollover) — Agent
- [ ] Persist minimal state (e.g., last weather snapshot) — Agent (nice-to-have)

## Observability & Logging
- [x] Add log level via env — Agent
- [x] Optional file logging to `DATA_DIR/bot.log` — Agent
- [ ] Systemd journal check instructions — Human

## Security
- [ ] Confirm permissions on `/opt/winter_wellness_bot` and `DATA_DIR` — Human
- [ ] Validate inputs from HTTP sauna source — Agent
- [ ] Secret management (tokens) via environment or systemd drop-in — Human

## Deployment
- [x] Example `systemd` unit verified and included — Agent
- [x] Add simple install script (create venv, copy files, permissions) — Agent
- [ ] Optional Dockerfile for non-Pi environments — Agent (optional)

## Testing & QA
- [x] Add minimal test harness (pytest) for key helpers — Agent
- [x] CI config (lint/tests) — Agent
- [ ] Manual E2E test on target Pi — Human

---

Completed by agent in this pass:
- Dotenv support + env auto-loading
- Data dir auto-creation
- Persist chat id on /start + scheduled fallback
- README updates reflecting above
- Added .gitignore
- Added .env.example
- Added interactive install script for Raspberry Pi
- Unified TODO (removed duplicate), removed stray artifacts
