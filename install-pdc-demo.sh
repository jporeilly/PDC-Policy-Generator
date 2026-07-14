#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Policy Generator — install/update inside the lab VM's PDC-Demo folder
#
# PDC-Demo is the Glossary repo's checkout (it holds glossary_generator/ and
# data_sources/). This script checks that folder exists, then:
#   - first run:  SPARSE-clones this repo (app only) into a hidden
#                 .pdc-policy-generator/ and links it FLAT at the top level:
#                 PDC-Demo/policy_generator + README-Policy.md
#                 (an old PDC-Policy-Generator/ layout is migrated in place)
#   - thereafter: pulls the latest (fast-forward only)
# and finishes with the offline selftest, so you know the app is healthy.
#
#   ./install-pdc-demo.sh                     # uses ~/PDC-Demo
#   ./install-pdc-demo.sh /path/to/PDC-Demo   # explicit location
#   ./install-pdc-demo.sh CSCU                # ALSO pull that vertical's
#                                                  # courseware (PDC-Scenarios)
#   PDC_DEMO_DIR=/srv/PDC-Demo ./install-pdc-demo.sh
#
# Verticals: with a PDC-Scenarios checkout in PDC-Demo, the currently
# selected vertical is detected from its sparse state and refreshed on every
# run; pass an ID (CSCU/RETAIL/HEALTH/MFG) to select or switch.
#
# One-liner on a fresh VM (no checkout of this repo needed):
#   curl -fsSL https://raw.githubusercontent.com/jporeilly/PDC-Policy-Generator/main/install-pdc-demo.sh | bash
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_URL="${POLICY_REPO_URL:-https://github.com/jporeilly/PDC-Policy-Generator.git}"
APP_DIR_NAME=".pdc-policy-generator"   # hidden clone; policy_generator symlinks to it at the top level

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

DEMO="${PDC_DEMO_DIR:-$HOME/PDC-Demo}"
VERTICAL="${VERTICAL:-}"
for arg in "$@"; do
  if [ -d "$arg" ]; then DEMO="$arg"
  else VERTICAL="$(printf '%s' "$arg" | tr '[:lower:]' '[:upper:]')"
  fi
done

printf "\n${TEAL}${B}  Policy Generator — install into PDC-Demo${RS}\n"
printf "${DIM}  Clone or update ${APP_DIR_NAME} inside the lab checkout.${RS}\n\n"

# --- pre-flight ------------------------------------------------------------
printf "${B}  Pre-flight${RS}\n"
command -v git >/dev/null 2>&1 || die "git is not installed."
ok "git $(git --version | awk '{print $3}')"

[ -d "$DEMO" ] || die "PDC-Demo folder not found: $DEMO   (pass the path: ./install-pdc-demo.sh /path/to/PDC-Demo)"
ok "PDC-Demo folder: $DEMO"

if [ -d "$DEMO/glossary_generator" ]; then
  ok "Looks like the Glossary checkout (glossary_generator/ present)"
else
  warn "No glossary_generator/ in $DEMO — continuing, but the Registry auto-discovery expects the Glossary app beside this clone"
fi
echo

# --- clone or pull ----------------------------------------------------------
printf "${B}  Policy Generator${RS}\n"
TARGET="$DEMO/$APP_DIR_NAME"
# migrate the old visible layout (PDC-Policy-Generator/) to the hidden clone
if [ -d "$DEMO/PDC-Policy-Generator/.git" ] && [ ! -d "$TARGET" ]; then
  mv "$DEMO/PDC-Policy-Generator" "$TARGET"
  ok "Migrated PDC-Policy-Generator/ -> $APP_DIR_NAME/"
fi
if [ -d "$TARGET/.git" ]; then
  printf "  ${DIM}existing clone — pulling…${RS}\n"
  git -C "$TARGET" pull --ff-only || die "pull failed — local changes in $TARGET? Commit/stash them and re-run."
  ok "Updated to $(git -C "$TARGET" rev-parse --short HEAD)"
elif [ -e "$TARGET" ]; then
  die "$TARGET exists but is not a git clone — move it aside and re-run."
else
  printf "  ${DIM}first run — sparse clone (app only)…${RS}\n"
  git -C "$DEMO" clone -q --filter=blob:none --sparse "$REPO_URL" "$APP_DIR_NAME"
  git -C "$TARGET" sparse-checkout set policy_generator
  ok "Cloned (app only — courseware/docs stay off the VM)"
fi

# flat view at the top level: policy_generator/ beside glossary_generator/,
# and the app's own README kept separate as README-Policy.md
ln -sfn "$APP_DIR_NAME/policy_generator" "$DEMO/policy_generator"
cp -f "$TARGET/README.md" "$DEMO/README-Policy.md" 2>/dev/null || true
ok "policy_generator/ linked at the top level (README-Policy.md beside it)"
# nested repo + generated entries stay out of the outer repo's git status
if [ -d "$DEMO/.git" ]; then
  for entry in "$APP_DIR_NAME/" "policy_generator" "README-Policy.md"; do
    grep -qx "$entry" "$DEMO/.git/info/exclude" 2>/dev/null || echo "$entry" >> "$DEMO/.git/info/exclude"
  done
fi

VER="$(cat "$TARGET/policy_generator/VERSION" 2>/dev/null | tr -d '[:space:]' || true)"
[ -n "$VER" ] && ok "App version: $VER"
echo

# --- verify ------------------------------------------------------------------
printf "${B}  Verify${RS}\n"
PY="$(command -v python3 || command -v python || true)"
if [ -n "$PY" ]; then
  if (cd "$TARGET" && "$PY" -m policy_generator.selftest >/dev/null 2>&1); then
    ok "Offline selftest passed"
  else
    warn "Selftest failed — run it for detail: cd $TARGET && $PY -m policy_generator.selftest"
  fi
else
  warn "Python 3 not found — install it before running the app"
fi
echo

# --- vertical courseware (PDC-Scenarios) -------------------------------------
printf "${B}  Vertical courseware (PDC-Scenarios)${RS}\n"
SCEN_URL="${SCENARIOS_REPO_URL:-https://github.com/jporeilly/PDC-Scenarios.git}"
SCEN_DIR="$DEMO/PDC-Scenarios"
if [ ! -d "$SCEN_DIR/.git" ] && [ -n "$VERTICAL" ]; then
  printf "  ${DIM}cloning PDC-Scenarios (sparse, %s only)…${RS}\n" "$VERTICAL"
  # --no-checkout: never materialize the full tree — set the sparse paths
  # first, then check out only the selected vertical (+ shared lab)
  git -C "$DEMO" clone -q --filter=blob:none --no-checkout "$SCEN_URL" PDC-Scenarios
  git -C "$SCEN_DIR" sparse-checkout set "data_sources/lab" "data_sources/$VERTICAL" "courseware/$VERTICAL" "diagrams"
  git -C "$SCEN_DIR" checkout -q
  if [ -d "$DEMO/.git" ] && ! grep -qx "PDC-Scenarios/" "$DEMO/.git/info/exclude" 2>/dev/null; then
    echo "PDC-Scenarios/" >> "$DEMO/.git/info/exclude"
  fi
fi
if [ -d "$SCEN_DIR/.git" ]; then
  git -C "$SCEN_DIR" pull -q --ff-only >/dev/null 2>&1 || warn "PDC-Scenarios pull failed (local changes?)"
  # which vertical is selected? the sparse set has data_sources/<ID> beside lab
  CUR="$(git -C "$SCEN_DIR" sparse-checkout list 2>/dev/null | sed -n 's#^data_sources/##p' | grep -v '^lab$' | head -1 || true)"
  [ -n "$VERTICAL" ] || VERTICAL="$CUR"
  if [ -n "$VERTICAL" ]; then
    if (cd "$SCEN_DIR" && bash select-vertical.sh "$VERTICAL" >/dev/null); then
      # flat view: courseware/ at the top level beside the apps
      ln -sfn "PDC-Scenarios/courseware" "$DEMO/courseware"
      grep -qx "courseware" "$DEMO/.git/info/exclude" 2>/dev/null || echo "courseware" >> "$DEMO/.git/info/exclude"
      ok "Vertical $VERTICAL — courseware/$VERTICAL + data kit pulled (courseware/ linked at the top level)"
    else
      warn "select-vertical.sh $VERTICAL failed — is '$VERTICAL' a valid scenario id?"
    fi
  else
    warn "No vertical selected yet — pick one: $0 CSCU   (or RETAIL/HEALTH/MFG)"
  fi
else
  warn "No PDC-Scenarios checkout — pass a vertical to set one up: $0 CSCU"
fi
echo

printf "${B}  Next${RS}\n"
printf "  ${TEAL}cd $DEMO/policy_generator && bash run.sh --host 0.0.0.0${RS}\n"
printf "  ${DIM}then open http://<vm-ip>:5001 — the Registry is auto-discovered from ../glossary_generator/registries/${RS}\n\n"
