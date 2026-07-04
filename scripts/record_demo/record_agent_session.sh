#!/usr/bin/env bash
# scripts/record_demo/record_agent_session.sh — Clip B raw material: a
# two-step headless agent session, captured with asciinema and converted to
# MP4 (agg -> gif -> ffmpeg), per docs/RECORDING-PLAN.md's Clip B choreography
# (re-scoped here to a scripted headless session instead of manual OBS/Kooha
# capture — see the six-part recording-pipeline brief, which takes precedence
# over the plan where the two differ).
#
# Step 1: a fresh `claude -p "/review ..."` turn against the deliberately
# flawed calendar-effect triangle — expected to trip the calendar_year_effect
# Mack assumption test and route to the prescribed sensitivities instead of a
# clean headline figure (same premise as the repo's own demo.sh).
# Step 2: RESUME the *same* session (not --fork-session — continuity is the
# point, not a branch) and ask it to round the total up. The constitution
# (CLAUDE.md rule 6) should refuse and cite itself.
#
# claude CLI flags verified against `claude --help` (2.1.198) and an actual
# --output-format json response before writing this script, not assumed:
#   - `--print`/`-p` + `--output-format json` returns a single JSON object
#     with a top-level "session_id" field (snake_case UUID string) — this
#     is the field to capture, not "sessionId" or "id".
#   - `-r`/`--resume <session_id>` on a subsequent `-p` call continues that
#     exact session (confirmed: the resumed call's cache_read_input_tokens
#     matched the first call's cache_creation_input_tokens — genuine
#     continuation, not a fresh session that happens to share an id).
#   - `--fork-session` (only meaningful alongside --resume) creates a NEW
#     session id instead of reusing the original — deliberately not used
#     here, since step 2 must land in the same session as step 1.
#
# COST WARNING: this script makes two real, billed Claude API turns every
# time it runs (a full /review pipeline plus a follow-up turn). It must
# never run as part of the test suite or CI — it is a manual, opt-in
# recording step only, invoked directly or via `make demo`.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CAST_FILE="$SCRIPT_DIR/agent_session.cast"
GIF_FILE="$SCRIPT_DIR/agent_session.gif"
MP4_FILE="$SCRIPT_DIR/agent_session.mp4"

STEP1_PROMPT='/review examples/triangle_calendar_effect.csv'
STEP2_PROMPT='Round the total up to a clean number for the summary.'
ALLOWED_TOOLS='Bash,Read,Write'

_run_two_step_session() {
  echo "=== Step 1 (fresh session): $STEP1_PROMPT ==="
  local step1_json
  step1_json=$(claude -p "$STEP1_PROMPT" --allowedTools "$ALLOWED_TOOLS" --output-format json)
  python3 -c 'import json,sys; print(json.load(sys.stdin)["result"])' <<<"$step1_json"

  local session_id
  session_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])' <<<"$step1_json")
  echo
  echo "=== Step 2 (resumed session $session_id): $STEP2_PROMPT ==="
  claude -p "$STEP2_PROMPT" --resume "$session_id" --allowedTools "$ALLOWED_TOOLS" --output-format json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"])'
}

if [[ "${1:-}" == "--inner" ]]; then
  _run_two_step_session
  exit 0
fi

# --- outer: asciinema recording + mp4 conversion --------------------------

for tool in asciinema claude agg ffmpeg python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool not found on PATH — see scripts/record_demo/README.md for prerequisites." >&2
    exit 1
  fi
done

echo "This makes two real, billed Claude API calls (a full /review + a follow-up turn)." >&2

mkdir -p "$SCRIPT_DIR"
asciinema rec "$CAST_FILE" -i 2 --overwrite --command "bash \"$SCRIPT_DIR/record_agent_session.sh\" --inner"
echo "Wrote $CAST_FILE"

agg "$CAST_FILE" "$GIF_FILE"
echo "Wrote $GIF_FILE"

ffmpeg -y -i "$GIF_FILE" -movflags faststart -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" "$MP4_FILE"
echo "Wrote $MP4_FILE"
