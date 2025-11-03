#!/usr/bin/env bash
set -euo pipefail

# Winter Wellness Bot — Raspberry Pi installer
# - Creates system user, directories and virtualenv
# - Prompts for configuration and writes /opt/winter_wellness_bot/.env
# - Installs systemd unit and starts the service

REPO_DIR="$(cd "$(dirname "$0")/.." 2>/dev/null || pwd)"
SRC_DIR="$REPO_DIR/winter_wellness_bot"
GITHUB_REPO="https://github.com/yishaik/winter-wellness-bot.git"
TARGET_DIR="/opt/winter_wellness_bot"
DATA_DIR_DEFAULT="/var/lib/winter_wellness_bot"
SERVICE_NAME="winter-wellness.service"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}"
USER_NAME="wellness"

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This script must run as root (use sudo)." >&2
    exit 1
  fi
}

prompt() {
  local var="$1"; shift
  local msg="$1"; shift
  local def="${1:-}"
  local value=""
  if [[ -n "$def" ]]; then
    read -r -p "$msg [$def]: " value || true
    value="${value:-$def}"
  else
    read -r -p "$msg: " value || true
  fi
  printf '%s' "$value"
}

prompt_secret() {
  local msg="$1"
  local value
  read -r -s -p "$msg: " value || true
  echo
  printf '%s' "$value"
}

create_user_and_dirs() {
  id "$USER_NAME" >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin "$USER_NAME"
  mkdir -p "$TARGET_DIR" "$DATA_DIR_DEFAULT"
  chown -R "$USER_NAME":"$USER_NAME" "$TARGET_DIR" "$DATA_DIR_DEFAULT"
}

install_prereqs() {
  apt-get update -y
  apt-get install -y python3-venv python3-pip git rsync curl ca-certificates tar
}

copy_app() {
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$SRC_DIR/" "$TARGET_DIR/"
  else
    cp -a "$SRC_DIR/." "$TARGET_DIR/"
  fi
  chown -R "$USER_NAME":"$USER_NAME" "$TARGET_DIR"
}

setup_venv() {
  cd "$TARGET_DIR"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
}

write_env_file() {
  local env_path="$TARGET_DIR/.env"
  echo "Writing $env_path"
  cat > "$env_path" <<EOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
TZ=${TZ_VAL}
LAT=${LAT_VAL}
LON=${LON_VAL}
SAUNA_SQLITE_PATH=${SAUNA_SQLITE_PATH}
SAUNA_BASE_URL=${SAUNA_BASE_URL}
SAUNA_TEMP_THRESHOLD_C=${SAUNA_TEMP_THRESHOLD_C}
SAUNA_MIN_DURATION_MIN=${SAUNA_MIN_DURATION_MIN}
MORNING_TIME=${MORNING_TIME}
EVENING_TIME=${EVENING_TIME}
DISABLE_MORNING=${DISABLE_MORNING}
DISABLE_EVENING=${DISABLE_EVENING}
DATA_DIR=${DATA_DIR}
LOG_LEVEL=${LOG_LEVEL}
LOG_TO_FILE=${LOG_TO_FILE}
MOOD_LOG_MAX_BYTES=${MOOD_LOG_MAX_BYTES}
EOF
  chown "$USER_NAME":"$USER_NAME" "$env_path"
  chmod 600 "$env_path" || true
}

install_service() {
  # Use the bundled unit file if present
  if [[ -f "$TARGET_DIR/winter-wellness.service" ]]; then
    cp "$TARGET_DIR/winter-wellness.service" "$UNIT_PATH"
  else
    cat > "$UNIT_PATH" <<EOF
[Unit]
Description=Winter Wellness Telegram Bot
After=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${TARGET_DIR}
EnvironmentFile=${TARGET_DIR}/.env
ExecStart=${TARGET_DIR}/.venv/bin/python ${TARGET_DIR}/main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
  fi
  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
  systemctl status "$SERVICE_NAME" --no-pager || true
}

main() {
  need_root
  echo "== Winter Wellness Bot Installer =="

  install_prereqs
  create_user_and_dirs

  # Detect source: if running from the repo tree, use it; otherwise clone from GitHub
  if [[ ! -f "$SRC_DIR/main.py" ]]; then
    echo "Source tree not found locally; cloning from $GITHUB_REPO"
    TMP_SRC="$(mktemp -d)"
    if command -v git >/dev/null 2>&1; then
      git clone --depth 1 "$GITHUB_REPO" "$TMP_SRC/repo"
      SRC_DIR="$TMP_SRC/repo/winter_wellness_bot"
    else
      TARBALL_URL="https://github.com/yishaik/winter-wellness-bot/archive/refs/heads/main.tar.gz"
      curl -fsSL "$TARBALL_URL" -o "$TMP_SRC/src.tar.gz"
      mkdir -p "$TMP_SRC/extracted"
      tar -xzf "$TMP_SRC/src.tar.gz" -C "$TMP_SRC/extracted"
      SRC_DIR="$(echo "$TMP_SRC"/extracted/winter-wellness-bot-*/winter_wellness_bot)"
    fi
  fi

  copy_app
  setup_venv

  echo
  echo "-- Configuration --"
  TELEGRAM_BOT_TOKEN=$(prompt_secret "Enter TELEGRAM_BOT_TOKEN (required)")
  if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
    echo "TELEGRAM_BOT_TOKEN is required." >&2
    exit 1
  fi
  TELEGRAM_CHAT_ID=$(prompt "TELEGRAM_CHAT_ID (optional; leave empty and /start in Telegram)" "" "")

  TZ_VAL=$(prompt "Timezone (TZ)" "Asia/Jerusalem")
  LAT_VAL=$(prompt "Latitude (LAT)" "32.0853")
  LON_VAL=$(prompt "Longitude (LON)" "34.7818")

  echo
  echo "Sauna data integration (choose one or leave empty):"
  SAUNA_SQLITE_PATH=$(prompt "SQLite DB path (e.g., /var/lib/sauna/sauna.db)" "")
  SAUNA_BASE_URL=$(prompt "HTTP base URL (e.g., http://127.0.0.1:5000)" "")

  SAUNA_TEMP_THRESHOLD_C=$(prompt "Sauna temp threshold °C" "45.0")
  SAUNA_MIN_DURATION_MIN=$(prompt "Min session minutes" "10")

  MORNING_TIME=$(prompt "Morning send time (HH:MM)" "09:00")
  EVENING_TIME=$(prompt "Evening send time (HH:MM)" "21:00")
  DISABLE_MORNING=$(prompt "Disable morning? (0/1)" "0")
  DISABLE_EVENING=$(prompt "Disable evening? (0/1)" "0")

  DATA_DIR=$(prompt "Data dir" "$DATA_DIR_DEFAULT")
  mkdir -p "$DATA_DIR"
  chown -R "$USER_NAME":"$USER_NAME" "$DATA_DIR"

  LOG_LEVEL=$(prompt "Log level (DEBUG/INFO/WARNING/ERROR)" "INFO")
  LOG_TO_FILE=$(prompt "Log to file? (0/1)" "1")
  MOOD_LOG_MAX_BYTES=$(prompt "Mood log max bytes (0 to disable)" "1048576")

  write_env_file
  install_service

  echo
  echo "Done. Verify the bot in Telegram. If TELEGRAM_CHAT_ID was empty, send /start to your bot to persist chat id."
  echo "To adjust settings later: edit ${TARGET_DIR}/.env and run: systemctl restart ${SERVICE_NAME}"
}

main "$@"
