---
description: Assemble (or regenerate) the review pack for an existing run
argument-hint: <run-id>
---

`reserve report` (Phase 5, the deterministic renderer) does not exist yet.
Until it does: assemble a markdown review for run `$1` following the
`reserving-report` skill's section structure (0–8) exactly, reading only
files already under `runs/$1/`. Do not re-run `fit` or change any
parameter as part of this command. If `diagnostics.json` or
`sensitivity.json` don't exist yet for this run, say so plainly rather
than fabricating their content — run them first only if that's what's
being separately asked for; `/report` itself should not silently change
what's been computed.

Once `reserve report <run-id> --format-out html|md` exists, replace this
body with a direct call to it — the skill then governs only the
*commentary* sections the renderer can't produce deterministically
(CLAUDE.md: "You may write the commentary sections of a review, but every
quantitative statement in your commentary follows rule 1").
