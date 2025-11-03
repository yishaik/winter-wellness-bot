#!/usr/bin/env python3
import os
import subprocess
import pwd
import grp
import stat
from typing import Dict, Tuple

from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import dotenv_values


def getenv_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


# Configuration of what we manage
MANAGED_DIR = os.getenv("MANAGED_DIR", "/opt/winter_wellness_bot").rstrip("/")
SERVICE_NAME = os.getenv("SERVICE_NAME", "winter-wellness.service")
ENV_FILE = os.path.join(MANAGED_DIR, ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "winter-wellness-webui")


def read_env() -> Dict[str, str]:
    if not os.path.exists(ENV_FILE):
        return {}
    try:
        data = dotenv_values(ENV_FILE)
        # dotenv_values returns OrderedDict with None for empty values; coerce to str
        return {k: ("" if v is None else str(v)) for k, v in data.items()}
    except Exception:
        return {}


def write_env(values: Dict[str, str]) -> None:
    # Preserve a consistent order for readability
    keys_preferred = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TZ",
        "LAT",
        "LON",
        "SAUNA_SQLITE_PATH",
        "SAUNA_BASE_URL",
        "SAUNA_TEMP_THRESHOLD_C",
        "SAUNA_MIN_DURATION_MIN",
        "MORNING_TIME",
        "EVENING_TIME",
        "DISABLE_MORNING",
        "DISABLE_EVENING",
        "DATA_DIR",
        "LOG_LEVEL",
        "LOG_TO_FILE",
        "MOOD_LOG_MAX_BYTES",
    ]
    lines = []
    for k in keys_preferred:
        if k in values:
            v = values[k]
            if v is None:
                v = ""
            # Basic escaping: wrap in quotes if contains spaces or special chars
            if any(ch in v for ch in [' ', '#', '"']):
                vv = '"' + v.replace('"', '\\"') + '"'
            else:
                vv = v
            lines.append(f"{k}={vv}")
    # Append any extra keys not in preferred list
    for k, v in values.items():
        if k in keys_preferred:
            continue
        if v is None:
            v = ""
        if any(ch in v for ch in [' ', '#', '"']):
            vv = '"' + v.replace('"', '\\"') + '"'
        else:
            vv = v
        lines.append(f"{k}={vv}")
    tmp_path = ENV_FILE + ".tmp"
    os.makedirs(MANAGED_DIR, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    # Attempt atomic replace
    os.replace(tmp_path, ENV_FILE)
    try:
        # Keep file reasonably private but group-writable for admin group
        os.chmod(ENV_FILE, 0o660)
    except Exception:
        pass


def run_cmd(cmd: list) -> Tuple[int, str]:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return 0, out
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output
    except Exception as e:
        return 1, str(e)


def systemctl(action: str) -> Tuple[int, str]:
    unit = SERVICE_NAME
    cmd = ["systemctl", action, unit]
    return run_cmd(cmd)


def service_status() -> Dict[str, str]:
    st = {}
    code, out = run_cmd(["systemctl", "is-active", SERVICE_NAME])
    st["active"] = out.strip() if out else ("error" if code != 0 else "unknown")
    code, out = run_cmd(["systemctl", "is-enabled", SERVICE_NAME])
    st["enabled"] = out.strip() if out else ("unknown")
    code, out = run_cmd(["systemctl", "status", SERVICE_NAME, "--no-pager", "--lines", "15"])
    st["status"] = out.strip()
    # Try journalctl for recent logs
    code, out = run_cmd(["journalctl", "-u", SERVICE_NAME, "-n", "200", "--no-pager", "--output", "short"])
    if code == 0:
        st["journal"] = out
    else:
        st["journal"] = f"(journalctl failed, code={code})\n{out}"
    # Fallback to bot.log if enabled
    env = read_env()
    data_dir = env.get("DATA_DIR", MANAGED_DIR)
    log_path = os.path.join(data_dir, "bot.log")
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-200:]
            st["bot_log"] = "".join(lines)
        except Exception:
            st["bot_log"] = "(failed reading bot.log)"
    else:
        st["bot_log"] = "(no bot.log found)"
    return st


def path_perm_info(path: str) -> Dict[str, str]:
    info: Dict[str, str] = {"exists": str(os.path.exists(path))}
    try:
        st = os.stat(path)
        info["mode"] = oct(st.st_mode & 0o777)
        try:
            info["owner"] = pwd.getpwuid(st.st_uid).pw_name
        except Exception:
            info["owner"] = str(st.st_uid)
        try:
            info["group"] = grp.getgrgid(st.st_gid).gr_name
        except Exception:
            info["group"] = str(st.st_gid)
        info["writable"] = str(os.access(path, os.W_OK))
        info["readable"] = str(os.access(path, os.R_OK))
    except FileNotFoundError:
        info.update({"mode": "-", "owner": "-", "group": "-", "writable": "False", "readable": "False"})
    return info


@app.route("/", methods=["GET"])
def index():
    env = read_env()
    # Defaults for UI fields if missing
    defaults = {
        "TELEGRAM_BOT_TOKEN": env.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": env.get("TELEGRAM_CHAT_ID", ""),
        "TZ": env.get("TZ", "Asia/Jerusalem"),
        "LAT": env.get("LAT", "32.0853"),
        "LON": env.get("LON", "34.7818"),
        "SAUNA_SQLITE_PATH": env.get("SAUNA_SQLITE_PATH", ""),
        "SAUNA_BASE_URL": env.get("SAUNA_BASE_URL", ""),
        "SAUNA_TEMP_THRESHOLD_C": env.get("SAUNA_TEMP_THRESHOLD_C", "45.0"),
        "SAUNA_MIN_DURATION_MIN": env.get("SAUNA_MIN_DURATION_MIN", "10"),
        "MORNING_TIME": env.get("MORNING_TIME", "09:00"),
        "EVENING_TIME": env.get("EVENING_TIME", "21:00"),
        "DISABLE_MORNING": env.get("DISABLE_MORNING", "0"),
        "DISABLE_EVENING": env.get("DISABLE_EVENING", "0"),
        "DATA_DIR": env.get("DATA_DIR", MANAGED_DIR),
        "LOG_LEVEL": env.get("LOG_LEVEL", "INFO"),
        "LOG_TO_FILE": env.get("LOG_TO_FILE", "0"),
        "MOOD_LOG_MAX_BYTES": env.get("MOOD_LOG_MAX_BYTES", "0"),
    }
    st = service_status()
    perm = path_perm_info(ENV_FILE)
    current_user = pwd.getpwuid(os.geteuid()).pw_name
    return render_template(
        "index.html",
        env=defaults,
        status=st,
        managed_dir=MANAGED_DIR,
        service_name=SERVICE_NAME,
        env_file=ENV_FILE,
        env_perm=perm,
        current_user=current_user,
    )


@app.route("/update", methods=["POST"])
def update():
    # Collect fields from form
    fields = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TZ",
        "LAT",
        "LON",
        "SAUNA_SQLITE_PATH",
        "SAUNA_BASE_URL",
        "SAUNA_TEMP_THRESHOLD_C",
        "SAUNA_MIN_DURATION_MIN",
        "MORNING_TIME",
        "EVENING_TIME",
        "DISABLE_MORNING",
        "DISABLE_EVENING",
        "DATA_DIR",
        "LOG_LEVEL",
        "LOG_TO_FILE",
        "MOOD_LOG_MAX_BYTES",
    ]
    values = {}
    for f in fields:
        values[f] = request.form.get(f, "").strip()
    try:
        write_env(values)
        flash("Configuration saved to .env", "success")
    except PermissionError as e:
        who = pwd.getpwuid(os.geteuid()).pw_name
        flash(
            (
                f"Permission denied writing {ENV_FILE}. Run WebUI as root, or adjust permissions. "
                f"Current user: {who}. Suggested: chgrp wellness {ENV_FILE} && chmod 660 {ENV_FILE} "
                f"or run: chgrp -R wellness {MANAGED_DIR} && chmod -R g+rwX {MANAGED_DIR} && usermod -aG wellness {who}"
            ),
            "error",
        )
    except Exception as e:
        flash(f"Failed saving .env: {e}", "error")
    return redirect(url_for("index"))


@app.route("/service", methods=["POST"])
def control_service():
    action = request.form.get("action", "")
    if action not in {"start", "stop", "restart", "reload", "enable", "disable"}:
        flash("Invalid action", "error")
        return redirect(url_for("index"))
    code, out = systemctl(action)
    if code == 0:
        flash(f"systemctl {action} succeeded", "success")
    else:
        flash(f"systemctl {action} failed: {out}", "error")
    return redirect(url_for("index"))


@app.route("/status", methods=["GET"])
def status():
    return service_status()


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    debug = getenv_bool("FLASK_DEBUG", False)
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
