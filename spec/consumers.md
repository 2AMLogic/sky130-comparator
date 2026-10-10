# Consumers

This file is this block's rule-9 record: it names every repo recorded as a
consumer of `sky130-comparator`, the requirement rows each consumer imposes,
whether this block's spec meets them, and the shape relationship — so an
integrator can answer *"does this block meet my requirements?"* from this
repo alone, without reading the consumer's decision records. (2am
cross-cutting rule 9, `2AMLogic/2am` `REUSE.md` §"Adopt or record",
ratified [2am#899](https://github.com/2AMLogic/2am/issues/899); the audit
that opened this file is issue #36.)

**Consumer set source of truth**: the `consumes:` entries naming
`sky130-comparator` in the fleet registry `repos.yml`. That file lived in
`2AMLogic/2am` until 2026-09-30 and now lives in the private fleet state
store [`2AMLogic/fleet-gitops`](https://github.com/2AMLogic/fleet-gitops)
(`2am`'s `repos.yml.MOVED` is the pointer). The snapshot this file was
written against is read live, not inherited from an older survey — see each
section's date stamp and the rule at
[Re-reading the consumer set](#re-reading-the-consumer-set) below.

**Snapshot status (refreshed 2026-10-10, issue #153).** Every verdict below
is a *dated snapshot*: it compares this repo as of `main` @ `daf6208` against
the consumer as of the revisions in the next section. It is not a standing
guarantee; both repos move. Each verdict states what it compares
(**bound** = a ratified/declared limit vs. the consumer's stated figure;
**measurement** = a recorded result vs. that figure), the **evidence stage**,
and its limitations. Evidence-stage vocabulary used throughout:

- **Ratified bound** — a target-spec row bound set by a decision record; a
  design limit, not a result.
- **Schematic** — measured on `design/comparator.sch`'s netlist (the DR-004
  static-preamp topology), append-only records under
  `sim/comparator-decision/records/`.
- **Historical post-layout** — measured on the parasitics-annotated
  extraction of an *earlier* committed layout (various klt/klayout pins and,
  for the first pass, the 0.42 µm-resistor layout; see `README.md` and
  `layout/README.md`). These characterize that geometry only.
- **Current-geometry post-layout** — extraction of the committed GDS at the
  klt 0.7.0 / klayout 0.30.12 pin with 0.35 µm resistors. **Not yet measured:**
  campaign [#125](https://github.com/2AMLogic/sky130-comparator/issues/125)
  (open, blocked on execution route
  [#127](https://github.com/2AMLogic/sky130-comparator/issues/127)). **No
  verdict below asserts compliance of the current geometry.**

The machine-readable half of this record — what an integrator takes, as
structured data — is [`manifests/integrator-view.json`](../manifests/integrator-view.json),
documented in [`manifests/README.md`](../manifests/README.md) and gated
against rot by `scripts/check-integrator-view.py` in CI.

## Consumers of record

Exactly **one**, as of 2026-10-10 (`fleet-gitops` `repos.yml` @ `main`
`e1fd8f88139b065f411dc7ce6f3c87666c0992d4`, committed 2026-10-10T15:58:12Z;
`sky130-sar-adc` entry, line 351, `consumes: [sky130-comparator]`; no other
entry carries it): **[`2AMLogic/sky130-sar-adc`](https://github.com/2AMLogic/sky130-sar-adc)** —
the nearest mature sibling, whose embedded comparator this repo
characterizes standalone. (Prior snapshot, 2026-09-22 from `2am` `repos.yml`
line 522: also exactly one — no consumer was added or removed; the file's
home moved.)

### 2AMLogic/sky130-sar-adc

**Sources and revisions read (2026-10-10).** Consumer repo `main` @
`fb8457cee88a110693f31a5ed8191adc55cf46d1` (2026-10-10T15:00:18Z).
Requirement sources, read in full for the comparator-relevant sections:
[`spec/target-spec.md`](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/target-spec.md)
(last changed in `6060111`, 2026-10-02) and the decision records
[DR-003](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-003-numeric-spec-derivation.md)
(accepted),
[DR-004 + Amendment A](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-004-comparator-topology-and-noise-budget.md),
[DR-006](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md),
[DR-009](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md),
and — new since the 2026-09-22 snapshot —
[DR-011](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-011-comparator-kickback-target-row.md),
[DR-014](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-014-comparator-kickback-mitigation-no-static-preamp.md),
[DR-016](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-016-kickback-headroom-neutral-mitigation-measurement.md),
[DR-020](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-020-comparator-offset-and-dead-band-spec-rows.md)
(header, status and decision sections). All of these are **`proposed`** in
the consumer except DR-003, which is accepted; the consumer's
target-spec rows other than those DR-003 ratified are DRAFT. Not re-read
for this refresh (unchanged relevance, stated so nobody assumes otherwise):
the consumer's remaining decision records (DR-001/005/007/008/010/012/013/
015/017–019/021) and its comparator-decision evidence records — the
consumer's own figures below are quoted from its documents, **not
re-measured here**.

Requirement rows, one per axis the rule names (plus Kickback, which the
consumer began requiring after the first snapshot). "Status" is whether
**this repo** meets the consumer's **stated** requirement, and every verdict
names the comparison kind and evidence stage. `unknown` is a legitimate
value.

| Axis | sky130-sar-adc's stated requirement (checked 2026-10-10) | This block's row | Verdict: compares / evidence stage / limits |
|---|---|---|---|
| Port list | **Not stated** as a standalone-block requirement. Context: the embedded comparator is driven differentially from the CDAC top plates; only `OUTP` (`COMP_OUT`) is consumed downstream; `OUTN` carries a matched dummy load (DR-009 §1). | `VDD`, `GND`, `CLK`, `VINP`, `VINN`, `OUTP`, `OUTN` — unchanged by DR-004 (the preamp is internally biased, no new port); netlisted flat, no `.subckt` wrapper (`manifests/integrator-view.json`). `CLK` drives the DR-003 soft-clock shaper, not a bare clock gate. | **unknown** — no requirement to compare against (nothing stated; no bound or measurement compared). Single-ended use of `OUTP` is mechanically possible; no compatibility claim. |
| Rails | 1.8 V core flavour (`nfet_01v8`/`pfet_01v8`), `V_REF = V_DD = 1.8 V`. No comparator power requirement stated (target-spec Power row: "provisional, minimise at rate", DRAFT). | 1.8 V ±10 % core supply, `nfet_01v8`/`pfet_01v8`. Supply/power sub-row **DRAFT/OPEN** (DR-002; unchanged by DR-004/DR-005 §5 — no current/power measurement exists). | **met on flavour and nominal rail** — *bound vs. stated figure*, ratified-bound stage (identical flavour). Power: **unknown**, nothing stated by the consumer and nothing measured here. |
| Input range | Input common mode fixed at `V_cm = V_REF/2 = 900 mV` by the differential top-plate CDAC (DR-003 Item 1; restated in DR-014 context). No range stated. | **No input-common-mode row** in the target-spec table. For context, every schematic bench biases `VINP`/`VINN` at `VCM = 0.9 V`, and DR-004 §3's static-preamp operating-point probe was run at that bias (input pair saturated with +0.876 to +1.008 V of Vds−Vdsat margin at the four probed corners `tt`/`ss` × 27/−40 °C; `ff`/125 °C not in that probe). | **unknown** as a spec compatibility — no bound on either side to compare. The schematic *measurements* happen to sit at 900 mV, so the consumer's point is exercised at schematic stage at the probed corners, but this block states no range and has no common-mode sweep, and no post-layout operating-point probe at all. (The consumer's headroom concern, DR-003 Item 1, was about a *stacked* latch input stage; this block's input stage is now the DR-004 preamp, so the consumer's 23.1 mV figure does not describe it and is not reused here.) |
| Speed | Provisional uniform phase allocation: one `CLK` period per conversion phase, `f_clk` 1.2–12 MHz ⇒ worst-case bit-trial phase budget ≈ 83.3 ns at 12 MHz (DR-006, **proposed**). No decision-time-vs-overdrive requirement stated; the consumer's own sequencer allocation is provisional and shares that phase with reset/precharge and logic. | Decision time ≤ 1.5 ns at 50 mV overdrive (stretch ≤ 0.8 ns), **RATIFIED (DR-005**, bounds unchanged from DR-002**)**. **Schematic** (DR-004 topology), seven PVT points: 0.3475–0.5375 ns at 50 mV, slowest `fs`/125 °C 0.5375 ns (DR-005 Decision 1). **Historical post-layout:** `tt`/27 °C 0.4025 → 0.5325 ns (#57, earlier geometry). | **likely compatible, with limits** — *ratified bound (1.5 ns) vs. the consumer's provisional budget (≈ 83.3 ns)* is ≈ 55×; the schematic *measurements* (≤ 0.5375 ns) are ≈ 155× inside it. Limits: the consumer's budget is provisional (DR-006 proposed) and shared; this block's figures are at **50 mV overdrive**, whereas late SAR bit trials see overdrives down to a fraction of the 3.5156 mV LSB, where regeneration time grows and the one sweep point that did not resolve (0.5 mV at `ss`/−40 °C, DR-004/DR-005) shows resolution is offset/noise-limited; no sub-LSB decision-time requirement exists to compare. Current-geometry post-layout speed is **pending #125**; the historical post-layout `tt` figure is not a statement about the present layout. The earlier "0.6775 / 0.6875 ns" figures this row once carried were the pre-DR-004 topology and are superseded. |
| Offset | **No numeric standalone-comparator requirement.** Half-LSB re-centering is a top-level scheme (DR-009 §2). DR-020 (**proposed**) decides *no offset row yet*: the consumer's own systematic decision offset is bounded `< 0.028 mV` and non-decision band `< 0.055 mV`, both far inside its half-LSB of 1.7578 mV; its random/mismatch σ is 97.08 mV (`W = 4 µm`, N = 16, one corner) and DR-020 declines to set a number pending an offset allocation and a precise σ. | Offset σ ≤ 15 mV 3σ (stretch ≤ 8 mV), **RATIFIED (DR-002)**. **Schematic**, DR-004 topology: N = 200, `tt_mm` σ = 2.1854 mV, `ss_mm` σ = 2.2353 mV (3σ ≈ 6.6–6.7 mV; DR-005 Decision 2). **Historical post-layout** (#57/#80): `tt_mm` σ 2.4446 mV and a layout-induced systematic term of 0.6350–0.6874 mV across the five `_mm` corners; DR-007 (**proposed**, not a bound) records a +1.875 mV systematic *decision* offset at `tt`/27 °C. | **unknown** — the consumer states no numeric requirement, so there is nothing to compare a bound or measurement against. Context only, not a verdict: this block's ratified 3σ bound (15 mV) and its schematic σ (≈ 2.2 mV) are both *above* the consumer's half-LSB scale of 1.7578 mV, so whether any future consumer offset allocation is met is **not** implied by "smaller than the consumer's 97 mV prior art" (different topology, sizing, sample size). An integrator who needs a comparator offset allocation should derive it from the consumer's error budget first (the open item DR-020 names). |
| Noise | ≤ 1.0148 mV rms (baseline) / ≤ 0.5859 mV rms (stretch), input-referred differential — the comparator's one-third share of the non-quantization budget (DR-003 Item 4, **ratified** in the consumer). | ≤ 1.0 mV rms differential (target), ≤ 0.6 mV rms (stretch), **RATIFIED (DR-002)**; target-bound compliance basis re-opened and re-closed by DR-006 + Amendment 1. **Schematic AC** (loop-broken preamp sub-model, a lower bound): 0.5704 mV rms `tt`/27 °C. **Schematic regeneration-inclusive** (`noise-tran`, DR-005): 0.1362 / 0.1213 / 0.1754 mV at `tt`/27, `ss`/−40, `ff`/125 °C. **Historical post-layout AC:** 0.4886–0.9423 mV across seven corners (`fs`/125 °C binds, 1.06× target margin, lower bound); **historical post-layout `noise-tran`:** `fs`/125 °C 0.2540 mV (DR-006 Amd 1), 0.1448 / 0.1382 / 0.1956 mV at `tt`/`ss`/`ff`; three corners unmeasured. | **Target: met bound-to-bound; stretch: not.** *Bound vs. requirement:* this block's 1.0 mV target is tighter than the consumer's 1.0148 mV baseline, but its 0.6 mV stretch is *looser* than the consumer's 0.5859 mV stretch, so the stretch is not guaranteed by the bound. *Schematic measurements* clear the consumer's baseline (0.5704 mV AC; 0.1754 mV worst `noise-tran` anchor) and, at the three graded `noise-tran` anchors, its stretch. *Historical post-layout AC* exceeds the consumer's stretch at the warm corners (up to 0.9423 mV) while staying under 1.0148 mV. Limits: the AC figures are lower bounds on a different (1 kHz–1 GHz integrated) basis than the decision-referred `noise-tran` figures, and the two bases disagree by ~3–4×; whether the consumer's 1.0148 mV is defined on the same bandwidth/basis as either was **not verified**. Current-geometry post-layout noise is **pending #125**. The earlier 0.4466 mV row (loop-broken pre-DR-004 latch sub-model) is superseded. |
| Kickback | **New since 2026-09-22.** ≤ 5 mV peak pin disturbance into a 1 kΩ series source, single decision edge (target); ≤ 2 mV (stretch) — **DRAFT** row (DR-011, **proposed**), adopted *verbatim* from this repo's ratified row as an interim choice, not derived from the consumer's budget. Consumer evidence: its own embedded comparator measures 73.3673 mV at `tt`/27 °C (baseline, one point; ≈ 14.7× the target). DR-014/DR-016 (proposed) did **not** adopt a static preamp or any mitigation there; row unchanged and unmet on the consumer side. | ≤ 5 mV / ≤ 2 mV, **RATIFIED (DR-002)**. **Schematic**, DR-004 topology (static preamp): 1.6091–2.0208 mV across seven graded corners; ≤ 5 mV cleared everywhere (2.5–3.1×), ≤ 2 mV breached by 1 % at `sf`/−40 °C (2.0208 mV) (DR-005 Decision 4). **Historical post-layout:** `tt`/27 °C 1.8902 → 2.6767 mV (#57, earlier geometry; stretch breached, target cleared 1.87×). | **Bound-to-bound identical by construction** (the consumer copied this repo's bound; they are the same number). *Schematic measurements* of this block's DR-004 design clear the target at every graded corner. Limits: the consumer's row is itself DRAFT/proposed; the 1 kΩ source and single-edge definition is the *same wording*, but whether the consumer's CDAC/top-level source impedance and edge actually match it was **not verified**; this block's figures are single-instance and schematic, with only a `tt`/27 °C historical post-layout point; the consumer's own comparator is a different topology (no preamp) and does not meet the row; current-geometry post-layout kickback is **pending #125**. This block does **not** claim the consumer's integrated instance meets, or could adopt this design to meet, the row — the preamp's consumer-side headroom cost is the consumer's DR-014 argument and is not re-evaluated here. |
| Area budget | **Not stated** (re-checked in the sources above). | A committed GDS exists (`layout/comparator.gds`); composed bbox 40.59 × 82.04 µm = 3330 µm² (`manifests/integrator-view.json`, `layout/compose-report.json`, issue #44). | **unknown** — the consumer states no area budget, so nothing to compare. The figure is a layout-envelope datum from the composed GDS (before any #125 re-measurement; it is not an electrical result). |

#### Shape note (recorded once, by name)

**Different topologies, separately sized instances.** The two comparators
are no longer the same class:

- **This block** (standalone, DR-004, which supersedes DR-001's "no static
  preamp" and double-tail-exclusion clauses): a continuously biased,
  resistive-load NMOS **static preamplifier** feeding a clocked
  StrongARM-class latch, behind the DR-003 soft-clock shaper. The preamp is
  what isolates the input pins from latch kickback.
- **The consumer** (embedded; its DR-004 + Amendment A, re-examined and
  kept by its DR-014/DR-016): a single-tail, NMOS-input dynamic latch with
  **no static preamp**, at a first-pass `W = 4 µm` input pair, with its
  DR-009 top-level output-load balancing and half-LSB offset wiring.

Earlier revisions of this file called them "same class" citing DR-001; that
was superseded by DR-004 on this side. They are not drop-in substitutes:
this block's measurements do not transfer to the consumer's instance, nor
the reverse, and the table above is the comparison of record. Adopting
this block's preamp in the consumer would overturn the consumer's DR-004
Decision §1 and is the consumer's decision to make, not a claim made here.

#### Findings routing

Findings about the **consumer's** comparator block are filed on the
consumer's tracker, not accumulated here — the worked pattern is
[sky130-sar-adc#346](https://github.com/2AMLogic/sky130-sar-adc/issues/346)
(this canary's kickback decomposition, filed there). This is
`CLAUDE.md`'s cross-pollination protocol restated where an integrator
looks; [`spec/porting-plan.md`](porting-plan.md)'s inventory of that repo's
comparator work carries the same line.

## Re-reading the consumer set

The fleet registry moves independently of this repo. The 2026-10-10
snapshot names exactly one consumer; when refreshing this file (a new
`consumes:` entry appears, an integrator asks, or this block's topology or
ratification state changes), re-read it live —
`gh api repos/2AMLogic/fleet-gitops/contents/repos.yml` (base64-decode the
`content` field; if that path moves, follow `2AMLogic/2am`'s
`repos.yml.MOVED` pointer) — and list every repo whose entry carries
`consumes: [sky130-comparator]`. Then add a section and row table per new
consumer, re-read each consumer's `spec/target-spec.md` and comparator
decision records (recording the repo revision and file revision, as above),
and update `manifests/integrator-view.json`'s provenance. Name whatever the
file says at that moment, not this snapshot. A consumer removal is likewise
recorded here as a dated note, never silently deleted. Any external source
that cannot be read at refresh time stays marked **unverified** with the
date it was tried.

Unverified at this refresh: the consumer's remaining decision records and
evidence records listed above as not re-read; equivalence of the consumer's
noise basis and kickback test conditions to this block's (see the Noise and
Kickback rows); the status of the consumer's follow-up issue #390 (its
common-mode/differential kickback split) since its target-spec last changed
on 2026-10-02.

The first snapshot (2026-09-22, issue #36, against `origin/main` `e084b55`)
is retained in git history; its Speed/Noise/Offset rows quoted the
pre-DR-004 topology and are superseded by this refresh.
