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

.PHONY: demo demo-tape demo-agent-session demo-report demo-assemble

demo: demo-tape demo-agent-session demo-report demo-assemble

demo-tape:
	vhs scripts/record_demo/demo.tape

demo-agent-session:
	scripts/record_demo/record_agent_session.sh

demo-report:
	python3 scripts/record_demo/record_report.py

demo-assemble:
	scripts/record_demo/assemble.sh
