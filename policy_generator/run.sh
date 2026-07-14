#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Policy Generator — launcher
#
# Reads the Glossary Generator's Classification Registry and manages PDC's
# Data Identification side of the contract: author the method set (patterns +
# dictionaries), then — as they ship — reconcile term ids, deploy over the
# public API, and drift-check deployed methods against the governed vocabulary.
#
# Creates a local virtualenv (.venv) and installs dependencies — re-installing
# only when requirements.txt changes, so repeat runs are fast. Nothing touches
# your system Python.
#
#   ./run.sh                 # http://127.0.0.1:5001
#   ./run.sh --port 8081     # choose a port
#   ./run.sh --host 0.0.0.0  # bind all interfaces (e.g. on a lab VM)
#   PORT=8081 ./run.sh       # env vars work too (HOST, PORT)
#   NO_COLOR=1 ./run.sh      # plain output
#   ./run.sh --help
#
# The default port is 5001 so the Glossary Generator (5000) can run alongside.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

# --- colours (auto-off when not a TTY or NO_COLOR is set) ------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\033[1m'; DIM=$'\033[2m'; RS=$'\033[0m'
  TEAL=$'\033[38;5;37m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'
else
  B=""; DIM=""; RS=""; TEAL=""; GREEN=""; YELLOW=""; RED=""
fi
ok(){   printf "  ${GREEN}✓${RS} %s\n" "$1"; }
warn(){ printf "  ${YELLOW}!${RS} %s\n" "$1"; }
die(){  printf "  ${RED}✗ %s${RS}\n" "$1" >&2; exit 1; }

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5001}"

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="${2:?--port needs a value}"; shift 2;;
    --host) HOST="${2:?--host needs a value}"; shift 2;;
    -h|--help) awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next}{exit}' "$0"; exit 0;;
    *) echo "Unknown option: $1 (try --help)"; exit 1;;
  esac
done

# --- banner ----------------------------------------------------------------
VER="$(cat VERSION 2>/dev/null | tr -d '[:space:]' || true)"
printf "\n${TEAL}${B}  Policy Generator${VER:+ v$VER}${RS}\n"
printf "${DIM}  Registry → Data Identification.  Author import-ready PDC patterns and\n"
printf "  dictionaries from the Glossary Generator's Classification Registry.${RS}\n\n"

# --- pre-flight checks -----------------------------------------------------
printf "${B}  Pre-flight${RS}\n"

PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || die "Python 3 is not installed or not on PATH."
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,9) else 1)'; then
  die "Python 3.9+ required. Found: $("$PY" --version 2>&1)"
fi
ok "Python $("$PY" -c 'import platform;print(platform.python_version())') ($PY)"

[ -f requirements.txt ] || die "requirements.txt not found — run this from the app folder."
[ -f app.py ]          || die "app.py not found — run this from the app folder."
ok "App files present"

# Port availability (best-effort; a busy port means bind will fail)
if "$PY" - "$HOST" "$PORT" <<'PYEOF' 2>/dev/null; then
import socket, sys
h, p = sys.argv[1], int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind((h if h != "0.0.0.0" else "", p)); s.close(); sys.exit(0)
except OSError:
    sys.exit(1)
PYEOF
  ok "Port $PORT is free on $HOST"
else
  warn "Port $PORT looks busy on $HOST — start with '--port <n>' if launch fails"
fi
echo

# --- virtualenv + dependencies (reinstall only when requirements change) ---
printf "${B}  Environment${RS}\n"
if [ ! -d .venv ]; then
  printf "  ${DIM}creating virtualenv (.venv)…${RS}\n"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

STAMP=".venv/.req-stamp"
REQ_HASH="$( (sha1sum requirements.txt 2>/dev/null || shasum requirements.txt) | awk '{print $1}')"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$REQ_HASH" ]; then
  printf "  ${DIM}installing dependencies…${RS}\n"
  python -m pip install -q --upgrade pip >/dev/null
  python -m pip install -q -r requirements.txt
  echo "$REQ_HASH" > "$STAMP"
  ok "Dependencies installed"
else
  ok "Dependencies up to date"
fi
echo

# --- launch ----------------------------------------------------------------
export HOST PORT
printf "${B}  Ready${RS}\n"
printf "  ${TEAL}${B}→ http://%s:%s${RS}   ${DIM}(Ctrl-C to stop)${RS}\n\n" "$HOST" "$PORT"
exec python app.py
