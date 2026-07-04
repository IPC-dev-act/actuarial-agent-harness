#!/usr/bin/env bash
# scripts/record_demo/assemble.sh — final assembly: normalise every clip to
# 1080p/30fps, concatenate tape -> agent session -> report review, and burn
# in the three captions per docs/RECORDING-PLAN.md / the recording brief.
#
# Caption START/END values are positions in the ASSEMBLED (post-concat)
# timeline, not any single source clip — they depend on the actual length of
# clips A and B-part-1 in your take. Re-measure and adjust after every
# re-record (`ffprobe scripts/record_demo/demo_final.mp4`, or just scrub the
# output). This is one of the two manual steps the pipeline still needs —
# see scripts/record_demo/README.md; everything else here runs unattended.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- captions: verbatim text -------------------------------------------
CAPTION_1="A diagnostic fired. The agent re-routes — it does not proceed."
CAPTION_2="Asked to shade the figure. It declines and cites its constitution."
CAPTION_3="Every number traces to a hashed, versioned run manifest."

# --- caption timestamps: seconds into the ASSEMBLED timeline ------------
# per-take-adjustable — edit these four numbers per caption after each
# re-record; nothing else in this script needs to change.
CAPTION_1_START=42
CAPTION_1_END=48

CAPTION_2_START=58
CAPTION_2_END=64

CAPTION_3_START=95
CAPTION_3_END=101

# --- inputs (produced by the earlier pipeline steps) --------------------
CLIP_A="${CLIP_A:-demo_cli.mp4}"                # from demo.tape (vhs)
CLIP_B1="${CLIP_B1:-agent_session.mp4}"         # from record_agent_session.sh
CLIP_B2="${CLIP_B2:-report_review.webm}"        # from record_report.py

OUTPUT="${OUTPUT:-demo_final.mp4}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found — see scripts/record_demo/README.md for prerequisites." >&2
  exit 1
fi

for f in "$CLIP_A" "$CLIP_B1" "$CLIP_B2"; do
  if [[ ! -f "$f" ]]; then
    echo "missing $f — run demo.tape / record_agent_session.sh / record_report.py first (or \`make demo\`)." >&2
    exit 1
  fi
done

# --- normalise: 1080p, 30fps, even dimensions, consistent pixel format --
_normalise() {
  local src="$1" dst="$2"
  # setsar=1 is required, not cosmetic: scale's force_original_aspect_ratio
  # can leave a slightly non-square SAR when the source aspect ratio doesn't
  # divide evenly (e.g. 800x450 -> 1920x1080), and ffmpeg's concat filter
  # refuses to join clips whose SAR values don't match exactly.
  ffmpeg -y -i "$src" \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p" \
    -an \
    "$dst"
}

_normalise "$CLIP_A"  "$TMP_DIR/a.mp4"
_normalise "$CLIP_B1" "$TMP_DIR/b1.mp4"
_normalise "$CLIP_B2" "$TMP_DIR/b2.mp4"

# --- concat (filter, not demuxer — inputs come from different encoders) -
CONCAT_FILE="$TMP_DIR/concat.mp4"
ffmpeg -y \
  -i "$TMP_DIR/a.mp4" -i "$TMP_DIR/b1.mp4" -i "$TMP_DIR/b2.mp4" \
  -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]" \
  -map "[outv]" \
  "$CONCAT_FILE"

# --- burn captions --------------------------------------------------------
# Escape single quotes and colons for ffmpeg's drawtext text= argument.
_esc() { printf '%s' "$1" | sed "s/'/\\\\'/g; s/:/\\\\:/g"; }

DRAWTEXT="drawtext=text='$(_esc "$CAPTION_1")':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.6:boxborderw=12:x=(w-text_w)/2:y=h-140:enable='between(t,${CAPTION_1_START},${CAPTION_1_END})'"
DRAWTEXT="${DRAWTEXT},drawtext=text='$(_esc "$CAPTION_2")':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.6:boxborderw=12:x=(w-text_w)/2:y=h-140:enable='between(t,${CAPTION_2_START},${CAPTION_2_END})'"
DRAWTEXT="${DRAWTEXT},drawtext=text='$(_esc "$CAPTION_3")':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.6:boxborderw=12:x=(w-text_w)/2:y=h-140:enable='between(t,${CAPTION_3_START},${CAPTION_3_END})'"

ffmpeg -y -i "$CONCAT_FILE" -vf "$DRAWTEXT" -c:v libx264 -pix_fmt yuv420p -movflags faststart "$OUTPUT"

echo "Wrote $SCRIPT_DIR/$OUTPUT"
