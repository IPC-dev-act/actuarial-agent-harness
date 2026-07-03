# corpus/

Ships empty by design. This directory exists to hold the primary-source
documents a deployment of this harness would cite against — it is not
populated in this public repo, on purpose, and that emptiness is itself the
governing state, not an oversight to fix later.

## The citation rule

CLAUDE.md rule 7: **regulatory statements are cited or not made.** Any claim
about a standard or a regulation must cite a document in this directory at
paragraph level, or it is refused — the same way an unsourced quantitative
figure is refused under rule 1. With `corpus/` empty, as it ships here, that
means **no regulatory or standards claim can currently be made at all**, full
stop. This isn't a gap to work around by reasoning more carefully or citing a
remembered general principle instead — the rule is unconditional on there
being an actual document to point at.

## The three-tier concept

A real deployment's `corpus/` would typically hold documents from three
distinct tiers, because a reserving figure can be examined against three
different kinds of external text, none of which substitute for another:

1. **Actuarial standards** — the professional body's own standards of
   practice for the work itself (e.g. ASOPs, an IFoA TAS, an IAA standard).
   These govern *how the analysis is done and documented* — methodology,
   disclosure, professional judgment.
2. **Prudential regulation** — the supervisory regime the entity reports
   under (e.g. Solvency II technical provisions requirements, a local
   regulator's reserving guidance). These govern *what a regulator requires
   the reserve figure to reflect and evidence*, independent of professional
   standards.
3. **Accounting bases** — the financial reporting standard the figure feeds
   into (e.g. IFRS 17, US GAAP LDTI, a local GAAP). These govern *how the
   reserve is measured and presented in financial statements*, which can
   differ materially from both of the above.

A claim citing one tier does not imply, and must not be narrated as if it
implied, agreement with either of the other two — they can and do disagree
with each other in practice (a figure fully compliant with one accounting
basis can still fail a prudential test, and vice versa). Cite the specific
tier and the specific paragraph the claim actually rests on.

## Populating this directory in your own deployment

Drop the specific documents your entity actually reports under — not a
general library "for reference." Recommended practice:

- One subdirectory per tier (`standards/`, `prudential/`, `accounting/`, or
  names matching your own governance taxonomy) so a citation's tier is
  legible from its path alone.
- Keep primary sources only, at a version/date you can name — a citation is
  only as good as knowing which edition of a standard it points to.
- Record provenance (source, edition/effective date, retrieval date) for
  each document, however lightly — a future reader needs to know a cited
  paragraph hasn't since been superseded.

Nothing under `corpus/` is read by any `reserve` command — this directory is
for the agent's citation discipline only (CLAUDE.md, the `reserving-report`
skill), never for engine input.
