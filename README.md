# actuarial-agent-harness

**A production harness for AI agents operating actuarial models.**

The model here is a commodity — the open-source, CAS-supported
[chainladder-python](https://github.com/casact/chainladder-python) package running a
Mack chain ladder. In your company it would be your internal reserving stack.
The harness is the asset: the agent constitution, the validation gates, the audit
manifests, the diagnostics discipline. **Swap the engine, keep the governance.**

AI belongs in actuarial work as a tool — not as an expert opinion. That opinion is
reserved for qualified actuaries. The failure mode to avoid is the black box:
figures coming out of an AI that we accept as-is, without understanding where they
came from. The intelligence is there to perform complex tasks correctly, as
defined — not to produce opinions that drive decisions, but to **inform** those
opinions with facts that are data-based and source-based, every one of them
traceable. This repository is a working demonstration of what that looks like in
practice.

**Who this is for:** anyone who runs, reviews, or governs actuarial models —
reserving actuaries, heads of modelling, model governance and audit, and the
engineers who build for them. It is a demo on public data: clone it, run it,
and judge whether the pattern would work with your models.

## The core principle

The agent is **extractive, not generative**. Every number it states is computed by
deterministic, tested code and traceable to an audit manifest. The agent controls,
narrates, and challenges — it never estimates, adjusts, or invents a figure.
If a Mack assumption test fails, the agent's job is to say so and propose which
sensitivity commands to run, not to override.

## Architecture

```
┌─────────────────────┐   ┌──────────────────────────────┐   ┌───────────────┐
│  ENGINE (swappable) │   │  HARNESS (the asset)         │   │  AGENT        │
│  chainladder-python │◄──│  reserve CLI · validation    │◄──│  Claude Code  │
│  or YOUR models     │   │  manifests · diagnostics     │   │  prompt-      │
│  (Prophet, Tyche,   │   │  CLAUDE.md · skills          │   │  controlled   │
│   internal Python)  │   │  deterministic HTML reports  │   │               │
└─────────────────────┘   └──────────────────────────────┘   └───────────────┘
```

A company adopts this by writing a ~100-line adapter for their engine
(see [ARCHITECTURE.md](ARCHITECTURE.md#engine-adapter-contract)) and inherits the
entire governance layer.

## Three ways to use this

Ordered by increasing agent autonomy — the same progression a real actuarial
department would follow.

### Layer 0 — No AI: run the model yourself

```bash
git clone https://github.com/<you>/actuarial-agent-harness
cd actuarial-agent-harness
pip install -e .
reserve validate examples/raa.csv
reserve fit examples/raa.csv --method mack --out runs/
reserve report <run-id> --format-out html
```

Pure Python. Inspect the deterministic engine first; confirm the numbers come from
code, not from a model.

### Layer 1 — Agent-assisted: Claude Code, zero configuration

```bash
claude
> Run a reserving review on examples/raa.csv
```

`CLAUDE.md` and the skills in `.claude/` are picked up automatically. The harness
travels with the repo — no installation of governance. Guided slash commands:

| Command | What it does |
|---|---|
| `/review <triangle.csv>` | Full pipeline: validate → fit → diagnostics → sensitivity if flagged → report |
| `/diagnose <run-id>` | Explain the Mack assumption tests on an existing run |
| `/challenge <run-id>` | Peer-review mode: the agent looks for weaknesses in the analysis |
| `/report <run-id>` | Regenerate the HTML review pack |

### Layer 2 — Unattended: headless run

```bash
./demo.sh   # claude -p "/review examples/triangle_calendar_effect.csv" ...
```

Note the demo data is **deliberately flawed**: the reproducible demo is the agent
detecting a violated assumption, refusing to override it, and running the prescribed
sensitivities instead.

## Verifiability

- **Against the literature**: the hero dataset is the RAA triangle from
  Mack (1994, CAS Spring Forum) — commonly misattributed to Mack (1993), which is
  a separate paper (the GenIns/Taylor–Ashe triangle's source, also bundled here).
  Development factors and standard errors are checked against the published papers —
  see [VALIDATION.md](VALIDATION.md).
- **Against reality**: the CAS Loss Reserve Database (`clrd`) sample includes
  subsequently observed outcomes, enabling `reserve backtest` (roadmap).
- **Against attack**: [docs/red-team.md](docs/red-team.md) logs adversarial
  prompts ("just estimate the tail factor", "the CFO needs a lower number")
  and the agent's actual refusals, verbatim — with a summary at the top for
  the verdict tally and the declared, not-yet-tested surface.
- **Every figure**: traceable to `runs/<id>/manifest.json` — input hash, package
  versions, parameters, timestamp.

## What this is not

Not a reserving product, not actuarial advice, and not a claim that agents should
sign reserve opinions. It is a reference implementation of the *harness pattern*
for letting agents operate models safely under professional standards.

## From demo to production

This repository is the pattern on public data. A production deployment adds:

- **An adapter to your engine** — and the data-extraction reality behind it:
  getting claims data out of your policy admin or claims system into a
  triangle the adapter can read is usually the larger effort, not the
  adapter itself.
- **Governance definitions for each additional method** — diagnostics,
  fixed narration, prescribed actions — matching what `mack` already has,
  for whichever of `docs/cli-spec.md`'s declared-not-governed roadmap
  entries you actually need.
- **Judgmental factor selection and tail fitting as governed inputs**, each
  deviation from the indicated factor carrying its own recorded rationale,
  not just the overridden number.
- **A populated regulatory corpus for your jurisdiction**, with the
  paragraph-level citation discipline `corpus/README.md` describes — the
  specific texts you report under, not a general library.
- **An IFRS 17 LIC bridge** — discounting and payment patterns as declared
  inputs, the risk adjustment derived from the stochastic output rather
  than picked, confidence-level traceability end to end.
- **Validation against your internal standards, not literature triangles**
  — RAA and GenIns confirm the engine is implemented correctly; they say
  nothing about your own book.
- **Adversarial testing against your own threat model** — the pressures and
  framings a red team would actually use inside your organisation, not
  this repository's public one.
- **Integration with your model-risk and audit framework** — this harness
  produces an audit trail; it doesn't attach itself to yours automatically.

This is the work I do — Ivan Perincic, IP Consulting.

## Data

All data is bundled or generated — a clean clone runs with no downloads:
classic literature triangles (RAA, GenIns) shipped with chainladder; the CAS Loss
Reserve Database sample (attribution: Casualty Actuarial Society); synthetic flawed
triangles generated by `scripts/make_flawed_triangles.py` with documented, seeded
pathologies. No client data of any kind.

## Requirements

- Layer 0: Python ≥ 3.10
- Layers 1–2: [Claude Code](https://docs.claude.com/en/docs/claude-code/overview)
  — tested with version `2.1.198`

## Credits & license

Built on [chainladder-python](https://github.com/casact/chainladder-python)
(MPL-2.0) by John Bogaardt, Kenneth Hsu and the CAS Open-Source Projects Working
Group. This repository: MIT.

Built by **Ivan Perincic** — IP Consulting ([FILL]),
Paris. 15+ years in life insurance capital and cash-flow modelling
(Prophet, Tyche, Solvency II, IFRS 17). Questions and ideas: LinkedIn,
[FILL], or open an issue — PRs welcome.
