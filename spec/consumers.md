# Consumers

This file is this block's rule-9 record: it names every repo recorded as a
consumer of `sky130-comparator`, the requirement rows each consumer imposes,
whether this block's spec meets them, and the shape relationship — so an
integrator can answer *"does this block meet my requirements?"* from this
repo alone, without reading the consumer's decision records. (2am
cross-cutting rule 9, `2AMLogic/2am` `REUSE.md` §"Adopt or record",
ratified [2am#899](https://github.com/2AMLogic/2am/issues/899); the audit
that opened this file is issue #36.)

**Consumer set source of truth**: [`2am/repos.yml`](https://github.com/2AMLogic/2am/blob/main/repos.yml)
`consumes:` entries naming `sky130-comparator`. The snapshot this file was
written against was read at build time (see each section's date stamp), not
inherited from an older survey — the rule for refreshing it is at
[Re-reading the consumer set](#re-reading-the-consumer-set) below.

The machine-readable half of this record — what an integrator takes, as
structured data — is [`manifests/integrator-view.json`](../manifests/integrator-view.json),
documented in [`manifests/README.md`](../manifests/README.md) and gated
against rot by `scripts/check-integrator-view.py` in CI.

## Consumers of record

Exactly **one**, as of 2026-09-22 (`repos.yml` @ `main`, line 522,
`consumes: [sky130-comparator]`, re-read at build time per issue #36):
**[`2AMLogic/sky130-sar-adc`](https://github.com/2AMLogic/sky130-sar-adc)** —
the nearest mature sibling, whose embedded comparator this repo
characterizes standalone.

### 2AMLogic/sky130-sar-adc

Requirement rows, one per axis the rule names. "Status" is whether **this
repo's spec** meets the consumer's **stated** requirement; `unknown` is a
legitimate value and every `unknown`/not-stated cell names where the
consumer was checked and when. The consumer's comparator-relevant decision
records were read for this table (not title-level):
[DR-003](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-003-numeric-spec-derivation.md),
[DR-004 + Amendment A](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-004-comparator-topology-and-noise-budget.md),
[DR-006](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md),
[DR-009](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-009-comparator-output-load-balance-and-half-lsb-offset.md),
all on 2026-09-22.

| Axis | sky130-sar-adc's stated requirement | Where stated (checked 2026-09-22) | This block's row | Status |
|---|---|---|---|---|
| Port list | **Not stated** as a standalone-block requirement. Integration facts, for context only: the embedded comparator is driven differentially from the CDAC top plates; only `OUTP` (`COMP_OUT`) is consumed downstream (sequencer `mux2_1`/`xnor2_1` inputs); `OUTN` carries a matched dummy load at the ADC top level. | DR-009 Decision §1 + DR-004 (full read incl. Amendment A); no standalone port-compatibility requirement found in either | `VDD`, `GND`, `CLK`, `VINP`, `VINN`, `OUTP`, `OUTN` (full-swing differential latch outputs; derived from `design/comparator.sch`) | **unknown** — no stated requirement to compare against; single-ended consumption of `OUTP` (the consumer's pattern) is mechanically possible, but no compatibility claim is made here |
| Rails | 1.8 V core flavour (`nfet_01v8`/`pfet_01v8`), `V_REF = V_DD = 1.8 V` at the rail. No comparator power requirement stated. | DR-001 (supply flavour, ratified in that repo) via DR-003 Item 1 (`V_REF = V_DD`); power checked absent in DR-003/DR-004/DR-009 | 1.8 V ±10 % core supply (`nfet_01v8`/`pfet_01v8`), **DRAFT/OPEN** row per DR-002 (power sub-row open: no measurement) | **met** on flavour and nominal rail (identical); the consumer states no power requirement to meet |
| Input range | Input common mode fixed at `V_cm = V_REF/2 = 900 mV` by the differential top-plate CDAC topology, whatever `V_REF` is chosen. | DR-003 Item 1 derivation ("the comparator's common-mode input is `V_cm = V_REF/2` in this topology"); DR-004 Context applies it | **Not stated** — the target-spec table (top-level `README.md`) has no input-common-mode row (checked the table + DR-001/DR-002/DR-003, 2026-09-22) | **unknown** — this block neither states an input-common-mode range nor has measured against a fixed-900 mV-Vcm stimulus; nothing here answers the 900 mV question yet |
| Speed | Provisional uniform phase allocation: every conversion phase gets one `CLK` period, `f_clk` 1.2–12 MHz ⇒ worst-case bit-trial phase budget ≈ 83.3 ns at 12 MHz. | DR-006 (uniform allocation + frequency range); DR-004 Amendment A cites it as "DR-006's provisional 83.333 ns worst-case bit-trial phase budget" | ≤ 1.5 ns at 50 mV overdrive, **DRAFT/OPEN** per DR-002 (full PVT sweep outstanding); measured 0.6775 ns (`tt`/27 °C) and 0.6875 ns (`ss`/−40 °C) at 50 mV overdrive | **met** at the measured points vs the consumer's provisional budget (~55× margin), with the caveat that this block's own row stays open pending the full PVT campaign (DR-002 Open items) |
| Offset | **No numeric standalone-comparator requirement.** The stated shape is half-LSB quantizer re-centering applied at the ADC top level (a reference-ratio unit cap switching `VREFP`→`VCM`), explicitly not a comparator-sizing obligation; output-load balancing is likewise handled at the top level. | DR-009 Decision §2 (offset shape) and Decision §1 (load balance) — full read; no numeric comparator offset row found in DR-003/DR-004/DR-009 | ≤ 15 mV 3σ input-referred, **RATIFIED** (DR-002); measured stdev 2.019 mV (3σ = 6.06 mV, N = 16, `tt_mm`) | **unknown** — the consumer states no numeric requirement to compare against. Context, not a requirement: the consumer's own embedded instance measured mean 35.24 mV / stdev 97.08 mV at first-pass sizing (`W = 4 µm`, N = 16, `tt_mm`, that repo's `sim/comparator-decision/records/`); this block's measured 3σ is ~16× below that stdev prior art |
| Noise | ≤ 1.0148 mV rms baseline / ≤ 0.5859 mV rms stretch, input-referred differential — the comparator's one-third share of the non-quantization noise budget under the equal three-way split. | DR-003 Item 4 (budget derivation, table row "Comparator input-referred noise"); DR-004 Decision §2 + Amendment A test it (post-amendment 0.6808 mV rms nominal; PASS vs baseline at every ratified corner, binding corner 0.8643 mV rms) | ≤ 1.0 mV rms differential, **RATIFIED** (DR-002); measured 0.4466 mV rms (`tt`, 27 °C, loop-broken sub-model — a lower bound by the same methodology DR-004 documents) | **met** vs the baseline: this block's ratified bound (1.0 mV) is tighter than the consumer's requirement (1.0148 mV) and its measurement (0.4466 mV) clears both. Note the stretch figures differ slightly (0.6 vs 0.5859 mV) and neither block has met its own stretch figure yet |
| Area budget | **Not stated.** | Checked absent in DR-003, DR-004 (+ Amendment A), DR-009 (full read of the comparator-relevant sections, 2026-09-22); no area row for the comparator exists in that repo's decision records | **Not produced** — no GDS exists (`layout/` holds only a README), no measured area; the integrator view carries explicit nulls | **unknown** — neither side states an area budget; nothing to compare until this block has a layout |

#### Shape note (recorded once, by name)

**Same class, separately sized instance.** Both comparators are single-tail,
NMOS-input dynamic latches with no static preamp — this repo per
[DR-001](decision-records/DR-001-comparator-topology.md), the consumer per
its [DR-004](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-004-comparator-topology-and-noise-budget.md)
(+ Amendment A). The consumer's instance is **embedded**: sized under its
DR-004 at a first-pass `W = 4 µm` input pair and integrated at the ADC's
port level (its DR-009 adds the top-level output-load balancing and
half-LSB offset wiring around it). This block is the **standalone
characterization** with its own DR-001/DR-003 sizing and the
[DR-003](decision-records/DR-003-kickback-slew-limited-clock.md) soft-clock
shaper. They are not the same block and not drop-in substitutes; the table
above is the comparison of record, so a reader does not re-derive the
relationship.

#### Findings routing

Findings about the **consumer's** comparator block are filed on the
consumer's tracker, not accumulated here — the worked pattern is
[sky130-sar-adc#346](https://github.com/2AMLogic/sky130-sar-adc/issues/346)
(this canary's kickback decomposition, filed there). This is
`CLAUDE.md`'s cross-pollination protocol restated where an integrator
looks; [`spec/porting-plan.md`](porting-plan.md)'s inventory of that repo's
comparator work carries the same line.

## Re-reading the consumer set

`repos.yml` is the source of truth and moves independently of this repo.
The 2026-09-22 snapshot names exactly one consumer; when refreshing this
file (a new `consumes:` entry appears, or an integrator asks), re-read it
live — `gh api repos/2AMLogic/2am/contents/repos.yml` (base64-decode the
`content` field) and list every repo whose entry carries
`consumes: [sky130-comparator]` — then add a section and row table per new
consumer here, and update `manifests/integrator-view.json`'s provenance.
Name whatever the file says at that moment, not this snapshot. A consumer
removal is likewise recorded here as a dated note, never silently deleted.
