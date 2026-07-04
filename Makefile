# Demo-video recording pipeline (scripts/record_demo/). See
# scripts/record_demo/README.md for prerequisites and the two manual steps
# this doesn't automate: choosing the best take, and adjusting assemble.sh's
# caption timestamps after a re-record.
#
# WARNING: `make demo` runs record_agent_session.sh, which makes two real,
# billed Claude API calls every time. Never wire this target into CI or run
# it unattended — it is a manual, opt-in recording step only.
#
# All recipes assume they're invoked from the repo root (Make's default —
# recipes run in the directory containing this Makefile).

.PHONY: demo demo-tape demo-agent-session demo-report demo-assemble tape-sync

demo: demo-tape demo-agent-session demo-report demo-assemble

demo-tape:
	vhs scripts/record_demo/demo.tape

demo-agent-session:
	scripts/record_demo/record_agent_session.sh

demo-report:
	python3 scripts/record_demo/record_report.py

demo-assemble:
	scripts/record_demo/assemble.sh

# Fits examples/raa.csv for real (reserve only — no claude, no recording
# tools), finds the run-id it just minted via `reserve runs list --format
# json` (sorted by run_id already, per docs/cli-spec.md — no need to trust
# filesystem mtime or scrape text with a regex), renders that run's report
# so demo.tape's own report step has a real target, then rewrites every
# run-id-shaped string in demo.tape to match. See
# scripts/record_demo/README.md's "make tape-sync" section.
tape-sync:
	reserve fit examples/raa.csv --method mack --out runs/ && \
	RUN_ID=$$(reserve runs list --out runs/ --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['runs'][-1]['run_id'])") && \
	reserve report "$$RUN_ID" --format-out html --out runs/ && \
	python3 scripts/record_demo/sync_tape_run_id.py "$$RUN_ID" && \
	echo "Synced scripts/record_demo/demo.tape to run-id: $$RUN_ID"
