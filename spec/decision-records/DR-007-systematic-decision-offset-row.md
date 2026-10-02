# DR-007: A systematic-decision-offset companion row for the Offset sigma spec

- **Status**: proposed
- **Date**: 2026-10-02
- **Decided by**: *not yet decided* — proposed by issue #66's Builder pass;
  ratification or rejection is an operator decision. Nothing in this record
  changes any ratified row, and nothing in it may be cited as a bound until
  its status becomes `ratified`.

## Context

DR-002 ratified the Offset sigma row as a **σ-only** bound (≤ 15 mV target /
≤ 8 mV stretch, 3σ, input-referred). Two facts measured since show that row
cannot express part of this block's post-layout offset behavior — not
because the bound is wrong, but because a dispersion statistic has no term
for a deterministic one:

1. Issue #57's post-layout `offset` campaign found the mismatch-disabled
   negative control's **mean** is 0.6547 mV on the extracted DUT (exactly
   0.0000 mV on the symmetric schematic fragment) — a systematic,
   layout-induced input-referred term, recorded in prose on the row with no
   line to grade it against.
2. Issue #66 has now measured the **decision-referred** quantity directly
   (`run.py offset-bisect`, bisecting the vindiff at which the decision
   flips polarity; records `20261002-000502-e2b808c.md`,
   `20261002-003713-e2b808c.md`, `20261002-002613-e2b808c.md`,
   `20261002-004906-e2b808c.md`):
   - `tt`/27 °C: schematic flip **−0.0391 mV** (negative control, ~0 by
     symmetry) vs. extracted flip **+1.8359 mV** — a **+1.875 mV
     layout-induced systematic decision offset**. The pick-off figure (1)
     and this figure disagree 2.8× in the same direction: they are
     different measurements (preamp stage at 0.65 ns vs. the whole
     regenerative decision), and the row that grades one does not grade
     the other.
   - `ss`/−40 °C: the extracted DUT has **no decision flip at all** — a
     28.2422 mV-wide **non-decision band** [−8.2715, +19.9707] mV (the
     schematic fragment's own band at that corner is symmetric
     ±0.8203 mV centered on 0). This is a decision-floor effect, not an
     offset; an offset bound is the wrong instrument for it, which is
     itself a reason to state it explicitly rather than fold it into a
     sigma.

CLAUDE.md bars agents from relaxing or changing a ratified spec to make
results pass; this record therefore **proposes** and changes nothing.

## Decision (proposed)

1. **Add a new target-spec row** — "Systematic decision offset
   (input-referred, decision-referred)" — measured by `offset-bisect` at
   the graded corners, schematic fragment as the ~0 negative control, with
   the proposed engineering-judgment bounds **target ≤ 2 mV**, **stretch
   ≤ 5 mV** (post-layout, `tt`/27 °C reference corner). The measured
   +1.8359 mV sits inside the proposed target with 1.09× margin — the
   bounds are drawn tight to the first measurement deliberately, so that
   ratifying them is a statement about the *as-drawn* layout rather than a
   blank check.
2. **Do not widen the Offset sigma row's meaning** — σ stays σ. The new row
   is a companion, not a redefinition; combined compliance of "3σ +
   |systematic|" is left for the ratifying record to decide (the simplest
   reading — grade them as separate rows — is what this proposal defaults
   to).
3. **Record the `ss`/−40 °C non-decision band as a stated limitation** on
   the Decision-time row's basis, not as an offset-row failure: the
   ratified Decision-time bounds are stated at 50 mV overdrive (which
   resolves at every graded corner), and the band means *sub*-28 mV
   positive overdrives do not decide at all post-layout at that corner.
   The proposed wording for the row's basis: "sub-20 mV post-layout
   decisions at `ss`/−40 °C sit inside a measured non-decision band
   (issue #66); bounds are unaffected at their stated 50 mV overdrive."
4. **Re-open question for the ratifier**: whether the other five graded
   corners need `offset-bisect` coverage before ratification (this pass
   measured the two anchor corners only, matching the `regen` anchors'
   coverage), and whether the cross-pollinated sky130-sar-adc embedded
   comparator should carry the same companion row.

## Alternatives considered

- **Fold the systematic term into the σ row (e.g. "3σ + |μ| ≤ 8 mV")** —
  rejected as a proposal: it silently changes a ratified row's meaning, and
  it cannot express the `ss`/−40 °C band at all.
- **No new row; keep recording the systematic term in prose** — rejected:
  the term is measured, deterministic, and design-relevant (it is what the
  sub-20 mV `regen` asymmetry was); prose has already demonstrably failed
  to keep it visible on the row it belongs to.
- **A pass/fail "resolvable overdrive floor" row instead of item 3's
  limitation note** — deferred: only one corner's floor is measured
  post-layout; a floor row needs the five-corner coverage this proposal
  leaves open (item 4).

## Spec lines affected

- `README.md` target-spec table: **adds** one row (Systematic decision
  offset) and appends a limitation sentence to the Decision time vs.
  overdrive row's basis — if and only if this record is ratified. Until
  then, no line changes.
- `sim/comparator-decision/run.py offset-bisect` is the measurement
  vehicle (already landed with issue #66); `sim/comparator-decision/README.md`
  documents it.

## Consequences

- Ratifying item 1 creates a new graded quantity with its own corner
  coverage question (item 4) — five more `offset-bisect` legs, each
  ~20 sequential decks at the extracted corners.
- The embedded-comparator consumers of this block (sky130-sar-adc) inherit
  the question of whether their decision overdrives ever sit inside a
  systematic-offset-shifted region — filed there per CLAUDE.md's
  cross-pollination protocol.
- Rejecting this proposal leaves the measured figures recorded in
  `sim/comparator-decision/README.md` and the six issue-#66 records; they
  remain true regardless of the spec's disposition.
