---
description: Explain scenario comparisons using scenario and comparison artifacts
argument-hint: <run-id> [scenario-id]
---

Apply the `reserving-scenario-compare` skill to run `$1`.

If a scenario id is provided, ensure `reserve scenarios $1 --format json` has
been run and then run `reserve compare $1 --scenario-id <scenario-id>
--format json` if the comparison artifact is missing or stale. If no scenario
id is provided, read `scenario_index.json`, `comparisons/*.json`, and any
committed `selection_sets/*.json` and summarize what comparisons are
available.

Use the standard operational output:

- What I ran
- What artifacts were created or read
- What I found
- What requires dashboard validation
- What I will not do without human decision
- Next step

Do not calculate deltas mentally, invent movement drivers, select a scenario,
or commit decisions. Every quantitative statement must cite an artifact under
`runs/$1/`.
