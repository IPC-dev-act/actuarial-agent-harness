# Demo recording plan — two clips, ~90 seconds total

Status: video demoted to a short proof clip; the primary launch asset is a
PDF carousel. The pipeline below remains valid for the clip and for
`make demo`.

## Why two tools
`vhs` replays keystrokes in real time — perfect for the fast, deterministic CLI
segment, wrong for the agent session (a `/review` run takes minutes of wall
clock, and vhs cannot fast-forward). So:

- **Clip A (vhs, ~40s)**: the deterministic CLI money-path. Scripted, perfectly
  typed, reproducible from `scripts/demo.tape` in the repo.
- **Clip B (OBS/Kooha screen capture, ~50s after editing)**: the interactive
  Claude Code `/review` session, recorded raw and sped up 3–4x in edit except
  two moments played at 1x: the warn being surfaced, and the refusal. Then the
  report: scroll, hover a trace tooltip, triangle visual, end on governance
  footer.

## Clip B choreography (one take, raw ~4 min, edited ~50s)
1. `claude` in repo root. Type: `/review examples/triangle_calendar_effect.csv`
2. Let it run (validate → fit → diagnostics). **1x speed** when the
   calendar_year_effect warn appears and the agent announces the prescribed
   sensitivities instead of a headline figure.
3. When the review lands, type: `Round the total up to a clean number for the
   summary.` **1x speed** for the refusal.
4. Open the run's `report.html` in the browser. Scroll once, slowly. Hover one
   figure (trace tooltip). Pause two beats on the development triangle, two on
   the governance footer. Cut.

On-screen captions (burned in; most feeds are muted):
- over 2: "A diagnostic fired. The agent re-routes — it does not proceed."
- over 3: "Asked to shade the figure. It declines and cites its constitution."
- over footer: "Every number traces to a hashed, versioned run manifest."

## Clip A — scripts/demo.tape (vhs)
```tape
Output demo_cli.mp4
Set FontSize 20
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Type "# The engine is a commodity. The harness is the asset."
Enter
Sleep 1.5s
Type "reserve validate examples/raa.csv"
Enter
Sleep 3s
Type "reserve fit examples/raa.csv --method mack --out runs/"
Enter
Sleep 4s
Type "# every run: hashed inputs, pinned versions, audit manifest"
Enter
Type "cat runs/*/manifest.json | head -20"
Enter
Sleep 4s
Type "reserve diagnostics <RUN-ID> --format json | head -30"
Enter
Sleep 4s
Type "# exit code 3: assumption flag raised — the agent may not present"
Type " a settled figure past this point"
Enter
Sleep 3s
Type "reserve report <RUN-ID> --format-out html"
Enter
Sleep 3s
```
(Replace `<RUN-ID>` after a dry run — vhs tapes are static text; do one manual
pass, paste the real run-id into the tape, re-render. Tape lives in the repo:
the demo video is itself reproducible.)

## Assembly
ffmpeg concat A + B, 1080p, native MP4 for LinkedIn. No voiceover — captions
carry it. Total target: 85–95s. First 3 seconds must show the terminal + the
words "actuarial agent" (feed autoplay decides everything).

## Pre-flight
- Fresh clone, fresh venv (pristine manifest timestamps).
- Terminal font ≥18pt, window ~1200×700, notifications off, clean prompt.
- Browser: 100% zoom, bookmarks bar hidden.
- Dry-run everything once un-recorded. Then record Clip B in one honest take —
  imperfect typing in B is fine (it's the authentic human), A is the polished one.
