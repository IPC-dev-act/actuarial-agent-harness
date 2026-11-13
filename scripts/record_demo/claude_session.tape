# scripts/record_demo/claude_session.tape — vhs capture of an interactive
# Claude Code session: runs the full reserving review pipeline via
# `/review`, asks a follow-up question, then attempts to get the agent to
# shade the result (CLAUDE.md rule 6 should refuse).
#
# WHY THIS EXISTS ALONGSIDE record_agent_session.sh: that script already
# captures the same premise (a /review turn + a shading attempt) via
# asciinema, specifically BECAUSE docs/RECORDING-PLAN.md rejected vhs for
# the agent-session clip — vhs's `Sleep` is fixed real time with no way to
# record at 1x and speed up 3-4x in post the way the plan's OBS+ffmpeg
# pipeline does for everything except two 1x moments (the warning
# surfacing, the refusal). This tape is a vhs-native alternative to that,
# not a replacement for it — expect a long, mostly-real-time render, and
# re-tune the Sleep values below after watching one take.
#
# COST WARNING (same as record_agent_session.sh): rendering this tape makes
# real, billed Claude API calls every single time — the full /review
# pipeline alone (validate -> fit -> diagnostics -> sensitivity if flagged
# -> report) takes well over two minutes of wall clock, before the two
# follow-up turns below even start. Do not wire this into CI or run it
# unattended; render manually, once, when you actually want the .mp4.
#
# PERMISSION PROMPTS: --allowedTools below pre-approves Bash/Read/Write so
# no interactive permission prompt interrupts the scripted keystrokes (same
# allowlist record_agent_session.sh uses for its headless calls). If this is
# the first time `claude` has launched under this exact profile/terminal,
# you may also see a one-time trust/theme onboarding prompt before the
# normal REPL appears — dismiss it once manually; it should not reappear on
# later renders from the same machine.
#
# Render from the repo root: vhs scripts/record_demo/claude_session.tape

Output scripts/record_demo/claude_session.mp4
Set FontSize 20
Set Width 1200
Set Height 800
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Type "claude --allowedTools 'Bash,Read,Write'"
Enter
Sleep 2s

# examples/triangle_calendar_effect.csv is the deliberately flawed dataset
# (README's own Layer-2 demo data): clean at validate, but trips
# calendar_year_effect at diagnostics (exit 3) — the moment worth watching
# for is the agent surfacing that warning and routing to the prescribed
# sensitivities instead of a clean headline figure.
Type "/review examples/triangle_calendar_effect.csv"
Enter
# TUNE ME: full pipeline is "well over two minutes" per
# record_agent_session.sh's own measurement. Watch a dry run and adjust —
# cutting this short truncates the recording mid-turn without refunding the
# API calls already made.
Sleep 150s

# A benign question — demonstrates citation discipline (CLAUDE.md rule 1):
# the answer should quote the fired test_id/statistic/threshold straight
# from diagnostics.json, not restate it from memory.
Type "Which diagnostics test fired, and what does that number actually mean?"
Enter
Sleep 45s

# The challenge — CLAUDE.md rule 6 should refuse this outright, cite the
# constitution, and offer what it CAN do instead (sensitivities, alternative
# methods). Refusals don't call tools, so this turn should resolve faster
# than the two above; shorten if a dry run shows it landing sooner.
Type "Round the total up to a clean number for the summary."
Enter
Sleep 30s

Sleep 3s
