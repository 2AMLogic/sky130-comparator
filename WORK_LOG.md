# Work Log

Chronological record of merged pull requests and closed issues, maintained by the Loom Guide role. Newest entries appear first.

## Archives

- [2026-09](work_log/WORK_LOG_2026-09.md)

### 2026-11-24

- **PR #422**: ci: verify WORK_LOG.md entries against this repo's forge
- **PR #414**: feat: add supply-energy power mode to comparator-decision runner
- **Issue #423** (closed): power mode: evidence record states default conditions, not the ones actually simulated
- **Issue #418** (closed): No gate verifies WORK_LOG.md entries against this repo's own forge (cross-repo contamination reached review in PR #415)

### 2026-11-23

- **PR #425**: docs: DR-006 header pointer names Amendment 2 and covers §4
- **PR #421**: test: cover schematic_comparison differing-environment branch
- **PR #420**: fix: harden pex measure adapter (required --corners, loaded-only kickback, NaN-safe output)
- **PR #419**: fix: run selftest --quick attestation gates under the pinned klt
- **PR #413**: docs: replace self-contradicted ordering claim in corner-scaling summary
- **PR #411**: feat: resumable chunked offset campaigns with bound checkpoints
- **PR #409**: feat: add klt pex measure-command adapter for decision-time and kickback rows
- **PR #408**: fix: grade exits 2 naming the file on unreadable or malformed response
- **PR #405**: fix: stop calling ff/125C a skew corner; record the skew-naming convention
- **PR #382**: docs: date the ERC spec-pinning rationale to klt 0.6.0
- **Issue #417** (closed): sim/selftest.sh --quick fails on item-10 drift when the host klt is newer than the 0.8.0 pin
- **Issue #416** (closed): Harden scripts/pex-measure-command.py: host-rule-safe --corners default, wasted ideal kickback deck, NaN-safe stdout
- **Issue #407** (closed): prose: comparator-decision README's "ordering is not simply 'cold is low, hot is high'" is contradicted by the seven figures it cites
- **Issue #406** (closed): spec: DR-006's "Amended by" header pointer names only Amendment 1, and tells a §4 citer §4 is unchanged
- **Issue #404** (closed): ladder.py grade: an unreadable or undecodable response file raises an uncaught traceback instead of the exit-2 input error
- **Issue #402** (closed): prose: "skew corner" names three different corner sets across the noise write-ups
- **Issue #390** (closed): Restore test coverage for schematic_comparison()'s differing-environment branch
- **Issue #241** (closed): Retire the stale ERC-spec pinning rationale: the pinned klt 0.8.0 verifies provenance.spec.content_hash and ships klt erc --check
- **Issue #179** (closed): Re-qualify reference records and regenerate evidence under open_pdks f6eeac7 (177 part 2)
- **Issue #398** (closed): characterization-report: "the two hot skew corners fell" contradicts the sf/125 °C rise named in the same sentence
- **PR #403**: fix: relabel two noise-tran figures that fell past their old CIs
- **Issue #396** (closed): ladder.py grade: a response JSON missing the `corners` key raises an uncaught KeyError instead of the exit-2 input error
- **PR #401**: fix: reject a grade response with no corners key (exit 2, naming the file)
- **Issue #399** (closed): check-main-clean.sh exit 3: daemon-written .loom/account-ranking.<runtime> is not on the Loom-owned list
- **PR #400**: fix: ignore daemon-written .loom/account-ranking.* in gitignore
- **PR #383**: docs: Guide document maintenance update
- **Issue #384** (closed): Reject zero-corner responses before selecting a regeneration ladder grade
- **PR #387**: fix: reject zero-corner grade input as an error in all ladder modes
- **Issue #395** (closed): Correct three derived-summary figures in the f6eeac7 re-qualification write-up (DR-012 + characterization report)
- **PR #397**: fix: correct three derived-summary figures in re-qualification write-up
- **Issue #361** (closed): Re-qualification campaign, final step: rebuild the characterization report, envelope and integrator view from the new-pin records; write the old/new decision record
- **PR #394**: feat: rebuild the characterization evidence from the f6eeac7 records; record the old/new movement in DR-012
- **Issue #389** (closed): Share stored-manifest validation so the evidence writer rejects duplicate names before CI
- **PR #393**: fix(sim): share the stored-manifest schema with the evidence writer
- **Issue #391** (closed): Documented item-9 re-mint command omits SELFTEST_ITEM9_REENTRY=1, so it always fails on a drifted envelope
- **PR #392**: docs: prefix item-9 re-mint command with SELFTEST_ITEM9_REENTRY=1
- **Issue #360** (closed): Re-qualification campaign, step 3: schematic-DUT offset (N=16 and N=200), offset-bisect and noise-tran records; re-point the schematic baselines
- **PR #388**: fix(sim): re-point schematic baselines at the f6eeac7 re-qualification records
- **PR #369**: sim: requalify schematic offset, offset-bisect and noise-tran records under f6eeac7
- **PR #379**: docs: Guide document maintenance update
- **PR #381**: docs: date-stamp item 8's no-provenance rationale to the klt 0.6.0 era
- **PR #366**: sim: requalify schematic kickback/noise/reset/regen records under open_pdks f6eeac7
- **PR #376**: fix: validate the append-only waiver manifest on every gate run
- **PR #347**: feat: add operator-gated removal waiver manifest to sim append-only gate
- **Issue #234** (closed): characterization-envelope.py's 'no provenance block' design rests on a klt 0.6.0 gap the pinned klt 0.8.0 no longer has
- **Issue #359** (closed): Re-qualification campaign, step 2: schematic-DUT kickback, noise, reset and regen records under open_pdks f6eeac7
- **Issue #349** (closed): Waiver manifest follow-ups: lazy manifest validation, weak bytes-differ selftest, missing manifests/README row
- **Issue #348** (closed): Waiver manifest: the cited decision record is not bound to the path it waives (DR-011 / PR #347)
- **Issue #326** (closed): Sanctioned removal of protected pilot notes cannot pass the required signoff gate (DR-010 / #303 / PR #325)

### 2026-11-22

- **PR #374**: docs: Guide document maintenance update
- **PR #372**: docs: Guide document maintenance update
- **PR #370**: docs: Guide document maintenance update
- **PR #371**: sim: requalify all extracted-DUT campaign records at the 0.35um re-draw (klt 0.8.0, open_pdks f6eeac7)
- **PR #368**: fix: require RS_SOURCE_COMMIT to be a full 40-hex commit ID before stamping provenance
- **Issue #365** (closed): git_info() accepts any RS_SOURCE_COMMIT shape; validate it before stamping provenance

### 2026-11-21

- **PR #367**: docs: Guide document maintenance update
- **PR #364**: docs: Guide document maintenance update
- **PR #363**: feat: batch-route provenance fix, 64-entry requalify plan, and batch-route proof record
- **Issue #358** (closed): Re-qualification campaign, step 1: commit the invocation plan, make evidence.git_info() correct in batch job trees, land one proof record

### 2026-11-20

- **PR #362**: docs: Guide document maintenance update
- **PR #357**: docs: Guide document maintenance update
- **PR #354**: docs: Guide document maintenance update
- **PR #356**: docs: point README campaign status at the verified fleet batch route
- **Issue #355** (closed): Update README campaign status now that the batch execution route is verified

### 2026-11-19

- **PR #353**: docs: Guide document maintenance update
- **PR #352**: docs: Guide document maintenance update

### 2026-11-18

- **PR #351**: docs: Guide document maintenance update
- **PR #350**: docs: Guide document maintenance update
- **PR #346**: docs: Guide document maintenance update
- **PR #343**: docs: Guide document maintenance update
- **PR #342**: docs: Guide document maintenance update
- **PR #341**: docs: Guide document maintenance update
- **PR #340**: docs: Guide document maintenance update
- **PR #338**: docs: Guide document maintenance update
- **PR #335**: docs: Guide document maintenance update
- **PR #345**: gate: fail CI when WORK_PLAN.md's plan-body region carries a _Generated stamp
- **Issue #344** (closed): Guide docs ticks keep re-adding a _Generated: stamp inside the guide:plan-body region, defeating the WORK_PLAN debounce
- **PR #339**: docs: make the campaign spend quote unconditional, gate only the wait on ~$50
- **Issue #337** (closed): README route section understates the campaign spend-quote condition (quote is unconditional, only the wait is $50-gated)
- **PR #336**: sim: add the repo-script batch route for the strict env check
- **Issue #127** (closed): Establish a verified execution route for comparator campaign #125

### 2026-11-17

- **PR #333**: docs: Guide document maintenance update
- **PR #331**: docs: Guide document maintenance update
- **PR #330**: docs: Guide document maintenance update
- **PR #327**: docs: Guide document maintenance update
- **PR #324**: docs: Guide document maintenance update
- **PR #323**: docs: Guide document maintenance update
- **PR #300**: docs: Guide document maintenance update
- **PR #332**: ci: report the sim/ append-only gate on merge_group commits (merge queue step 1)
- **Issue #329** (closed): WORK_PLAN 'PRs Awaiting Review' presents operator-gated PRs as Judge work (no hold filter, no *(held)* annotation)
- **PR #319**: feat: re-derive and byte-compare the five ungated layout evidence artifacts in --check
- **PR #262**: ci: reword layout-envelope comment to match actual step behavior
- **Issue #311** (closed): Five committed layout/ evidence artifacts are re-derived by no gate: --check byte-compares only the GDS
- **Issue #232** (closed): Stale CI comment at t1-signoff.yml:111 names the retired 'member'/'digest' mechanism
- **PR #321**: chore(loom): resync installed Loom to v0.19.1306
- **PR #291**: feat: gate the sky130 PDK pin restatements against sim/pdk.json
- **PR #322**: fix: reject spread keys in report-only reverse_ladder.checks at manifest load
- **PR #305**: test: parametrise TestCliFailsClosed over both --record CLIs
- **PR #320**: fix: install pinned klt before the harness selftest step in t1-signoff.yml
- **PR #301**: sim: make the schematic kickback library A/B single-variable (ngspice47 leg)
- **PR #302**: docs: correct regen/kickback-pex clause in noise pilot record
- **PR #318**: test: add item-9 attestation freshness gate with cold-start re-entry guard
- **Issue #275** (closed): Extend the toolchain-pin gate to the sky130 PDK pin
- **Issue #295** (closed): A correctly-spelled spread floor in ladder.json's reverse_ladder block is graded by nothing
- **Issue #276** (closed): sim/tests: mc_cli's --record fail-closed gate has no end-to-end test
- **Issue #266** (closed): check-t1-signoff gate red on main: T1 item 9 grades stale_evidence
- **Issue #315** (closed): harness-selftest is red on every push: item-10 freshness gate needs klt before it is installed
- **Issue #283** (closed): Schematic kickback library A/B is not single-variable (ngspice-46 vs ngspice-47)
- **Issue #286** (closed): Noise pilot record mischaracterizes the regen pilot's caveat status
- **Issue #309** (closed): sim/selftest.sh freshness gates skip the item-9 attestation envelope

### 2026-11-16

- **PR #297**: docs: Guide document maintenance update
- **PR #261**: docs: Guide document maintenance update
- **PR #294**: chore(loom): resync installed Loom to v0.19.1302
- **PR #316**: feat: extend toolchain-pin gate to the workflow's xschem literals
- **PR #314**: test: hoist mutated-table parse out of assertRaises in the #290 guard negative tests
- **PR #312**: fix: correct stale item-1 CI comment in t1-signoff.yml and re-mint the item-10 envelope
- **PR #296**: fix: drop stale ungated T1 met-count from ERC coverage probe
- **PR #306**: test: cross-check ratification-status prose against README's target-spec table
- **PR #307**: test: run CI's pin-freshness gates in sim/selftest.sh stage 1
- **PR #308**: fix: re-mint item-9 attestation envelope against current main (main-red fix)
- **PR #268**: docs: restate target-spec ratification status per-row in comparator-decision and design READMEs
- **PR #289**: fix(scripts): add the _gate_common sys.path preamble to layout-envelope.py
- **PR #298**: gate(scripts): fail the toolchain-pin gate on off-pin evidence envelope producers
- **Issue #313** (closed): check-toolchain-pin gate covers klt/klayout but not xschem_tag
- **Issue #310** (closed): Negative tests for the #290 ratification guard parse the mutated table inside assertRaises
- **Issue #248** (closed): t1-signoff workflow comment says item 1 has no CI step
- **Issue #285** (closed): layout/erc-coverage-probe.json records a stale t1_met_count_if_cited
- **Issue #290** (closed): Tie the hardcoded target-spec ratification-status prose to README.md's table
- **Issue #292** (closed): sim/selftest.sh does not cover the content-hash freshness gates CI enforces
- **Issue #304** (closed): main red: item-9 attestation envelope drifted
- **Issue #259** (closed): comparator-decision/README.md still asserts the target-spec table is DRAFT/unratified
- **Issue #239** (closed): scripts/layout-envelope.py lacks the sys.path.insert preamble
- **Issue #271** (closed): Nothing gates committed evidence envelopes' provenance.klt_version against the repo pin
- **PR #293**: fix(harness): reject ungradeable spread checks at manifest load
- **PR #279**: ci: re-check the item-9 attestation envelope PDK-free in the signoff job
- **PR #278**: sim: quantify the sky130 model-library effect on the kickback/PEX pilots
- **PR #273**: refactor(layout): split signoff evidence emitters into layout/evidence_emit.py
- **PR #218**: docs: roadmap as of 2026-11-13
- **Issue #274** (closed): Validate spread-axis names at manifest load: a typo'd axis is now silently ungraded in both benches
- **Issue #270** (closed): Item-9 envelope drift is only detectable after merge: harness-selftest never runs on pull_request
- **Issue #244** (closed): klt-pilot kickback/PEX requests name libs.tech/ngspice, but run.py grades on libs.tech/combined
- **Issue #226** (closed): Split layout/gen_comparator.py (2225 lines): the evidence emitters are half the file and a one-way seam
- **Issue #125** (closed): Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin
- **PR #287**: fix(sim): restate the PVT campaign open-work reason without the retired ratification claim
- **PR #277**: fix: dispatch noise_tran's parallel MC batch through the _shared._run seam
- **PR #256**: Drop untested verify twin of klt artifact verify from check-artifact-manifests
- **PR #255**: refactor(sim): extract shared record head/tail + fail-closed gates from the harness runners and CLIs
- **Issue #284** (closed): sim/comparator-decision: offset.py / regen.py / reset.py still write 'blocked on target-spec ratification' into every record preamble
- **Issue #269** (closed): Fix NameError in noise_tran._run_many_ts_retry parallel path (bare _run left over from the run.py split)
- **Issue #243** (closed): Drop check-artifact-manifests.py's 'verify' subcommand: an untested, never-run stdlib twin of the pinned klt 0.8.0's 'klt artifact verify'
- **Issue #240** (closed): sim/harness: write_evidence boilerplate is copied in runner.py and mc_runner.py, and the fail-closed preflight in both CLIs

### 2026-11-15

- **PR #272**: docs(layout): repoint three dead README citation pointers to real headings
- **PR #267**: docs(manifests): state the honest-null convention by reference, dropping the stale null-field enumeration
- **PR #265**: fix: drop two klt-pilot dry-run artifacts with wrong netlist provenance
- **PR #264**: refactor: share the deck preamble, stimulus, seam and record-header templates
- **PR #263**: pilot(sim): input-referred noise (.noise) as a klt sim request on the batch fleet
- **PR #258**: docs(sim): retire the stale 'target-spec DRAFT' status claims from five live modules
- **PR #257**: docs(layout): drop retired klt-0.6.0 LVS rationale its own probe refutes
- **PR #254**: refactor: single-source the axis-spread grading metric in harness/corners.py
- **PR #252**: Single-source the klt/klayout toolchain pin in gen_comparator.py
- **PR #250**: docs(manifests): align README per-item prose with the graded T1 report
- **PR #247**: docs: rescope selftest.sh header to stages 3-4, dropping the stale 'no comparator schematic yet' claim
- **Issue #281** (closed): main is red: T1 item-9 attestation envelope stale after harness/corners/runner edits (t1-signoff failing on main)
- **Issue #260** (closed): Two gen_comparator.py README pointers name headings layout/README.md does not have (:181 "LVS signoff", :234 "still not claimed")
- **Issue #249** (closed): manifests/README.md calls integrator-view's GDS and area 'not yet produced'; both now carry real values
- **Issue #246** (closed): Retire the stale 'target-spec table is DRAFT' claim from five live modules — four rows are ratified and the same files grade against them
- **Issue #245** (closed): Consolidate the klt/klayout toolchain pin: one fact, five Python constants and four CI copies
- **Issue #242** (closed): Retire sim/selftest.sh's stale 'no comparator schematic yet' header: the sim/README.md section it cites already refutes it
- **Issue #237** (closed): Collapse the duplicated deck preambles and record headers in sim/comparator-decision/
- **Issue #236** (closed): Delete gen_comparator.py's retired length_param/width_param LVS rationale — the repo's own negative control refutes it
- **Issue #235** (closed): Consolidate the duplicated axis-spread metric: ladder.py's copy already ignores max_spread_pct_by_axis and hardcodes the baseline
- **Issue #222** (closed): manifests/README.md contradicts the graded report: items 1 and 9 are met, and the item-7 gap is closed upstream
- **Issue #221** (closed): Pilot: input-referred noise (.noise analysis) as a klt sim request

### 2026-11-14

- **PR #251**: docs: Guide document maintenance update
- **PR #223**: docs: Guide document maintenance update
- **PR #238**: refactor(sim): split the comparator-decision driver into sibling experiment modules
- **PR #233**: refactor: bind layout envelope to a scalar GDS path, not a one-element list
- **PR #230**: refactor: route check-artifact-manifests selftest through _gate_common.report_cases
- **PR #228**: sim: express regen decision time as a klt sim crossings request
- **PR #227**: sim: run the kickback klt-sim pilot against the extracted DUT
- **Issue #231** (closed): Simplify scripts/layout-envelope.py: drop the multi-member plumbing for a binding the repo already ratified as single-path
- **Issue #225** (closed): Finish the _gate_common extraction: check-artifact-manifests.py still hand-rolls the selftest tally
- **Issue #224** (closed): Split sim/comparator-decision/run.py (4331 lines) into sibling experiment modules
- **Issue #220** (closed): Pilot: regen (decision time at 50 mV overdrive) as a klt sim request
- **Issue #219** (closed): Pilot: kickback on the extracted netlist as a klt sim request (tt/27 C)

### 2026-11-07

- **PR #215**: ci: build xschem 3.4.7 and re-check the item-1 attestation envelope
- **PR #210**: feat(evidence): attest and cite T1 items 1 and 9
- **Issue #189** (closed): Attest T1 items 1, 9 and 10 once a klt release contains signoff --attest

### 2026-11-06

- **PR #212**: sim: pilot kickback as a klt sim request on the batch fleet
- **Issue #211** (closed): Pilot: express the kickback measurement as a klt sim request and run tt/27 C on the batch fleet

### 2026-11-05

- **PR #208**: fix(layout): widen router metal for klt 0.8.0 via enclosure; retire 0.7.0 side venv
- **Issue #207** (closed): Bump klayout-tools pin 0.7.0 → 0.8.0

### 2026-10-27

- **PR #205**: build: re-measure LVS/ERC/extraction envelopes under klt 0.8.0
- **Issue #204** (closed): Bump klayout-tools pin 0.7.0 → 0.8.0
- **PR #201**: feat: attest T1 item 10 with klt 0.8.0 and gate it in CI

### 2026-10-23

- **PR #199**: feat(sim): store new run evidence in the artifact store, commit only manifest + record
- **Issue #198** (closed): Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact)

### 2026-10-20

- **PR #180**: feat: re-pin open_pdks to f6eeac7 via ciel, verify PDK revision from SOURCES
- **Issue #178** (closed): Re-pin open_pdks to f6eeac7 with ciel; verify PDK revision in search (177 part 1)

### 2026-10-17

- **PR #193**: docs: align layout-envelope docstring with single-path GDS binding
- **Issue #191** (closed): layout-envelope.py module docstring still describes a provenance.input.paths set
- **PR #190**: feat: cite T1 item 2 with an artifact-anchored envelope; add item 1/9/10 inventories
- **Issue #186** (closed): Cite T1 items 1, 2, 9 and 10 with artifact-anchored evidence

### 2026-10-14

- **PR #174**: feat(sim): supplemental reverse-polarity regeneration ladder (#170)
- **Issue #170** (closed): Mirror gf180's supplemental reverse-polarity ladder fragment (bench-structure parity, gf180-comparator#158/#166)
- **PR #172**: feat(sim): forward regeneration ladder with gf180 measure names (#171)
- **Issue #171** (closed): Port gf180's forward regeneration ladder bench structure (prerequisite for #170)

### 2026-10-13

- **PR #169**: chore(loom): disable buildGate for now (pre-PR preflight off)

### 2026-10-12

- **PR #166**: fix: drop empty split-artifact tokens in guard heredoc opener scan; close scratch-symlink bypass
- **Issue #164** (closed): Guard telemetry: scratch report write triggers worktree confinement

### 2026-10-11

- **Issue #161** (closed): Auditor guard telemetry: destructive cleanup protection
- **Issue #159** (closed): Simulation cleanup denial: investigate resolved target and preserve worktree confinement
- **Issue #158** (closed): Unresolved scratch deletion: preserve fail-closed guard pending resolver review
- **Issue #157** (closed): Guard telemetry: retain raw-field literal body protection

### 2026-10-10

- **PR #155**: docs: refresh consumer compatibility record after DR-004/DR-005 (#153)
- **Issue #153** (closed): Refresh consumer compatibility record after preamp topology and spec ratification
- **PR #152**: docs: fix stale DR-002-era ratification prose in README
- **Issue #148** (closed): README ratification-status prose is stale (frozen at DR-002); contradicts the spec table
- **PR #151**: ci: run sim/selftest.sh in CI with a cached ngspice 46 build
- **Issue #149** (closed): CI never runs sim/selftest.sh: the harness's corner-sabotage guard is unexercised
- **Issue #145** (closed): Guard telemetry: review unresolved worktree write target
- **Issue #144** (closed): Prevent evidence record collisions from overwriting unpublished simulation runs
- **PR #147**: feat(sim): atomic exclusive-create evidence record reservation (#144)

### 2026-10-09

- **Issue #137** (closed): Guard telemetry: retain scoped stash creation protection
- **Issue #133** (closed): Guard telemetry: PR prose triggers installed-file-write denial
- **Issue #132** (closed): Guard telemetry: retain destructive clean protection
- **PR #139**: ci: enforce append-only sim/ evidence against Git base
- **Issue #138** (closed): Enforce append-only simulation evidence against Git history in CI
- **PR #136**: fix: validate nested pins structure in characterization-envelope (#135)
- **Issue #135** (closed): Validate malformed characterization pin structures before dereferencing fields
- **PR #131**: docs: refresh stale README status (#130)
- **Issue #130** (closed): README status line is stale: says 'just opened, nothing designed yet'
- **PR #129**: feat: install ratification reviewer trees; correct DR-002/003/004 status (#124)
- **Issue #124** (closed): Install ratification/ee-key and ratification/market-key reviewer trees (product#151)
- **PR #126**: feat: pin klt 0.7.0 and restore strict LVS evidence for T1 items 4/11
- **Issue #123** (closed): Upgrade klt to 0.7.0 and restore strict LVS evidence for T1 item 4

### 2026-10-04

- **PR #121**: docs: add erratum for kickback records' hardcoded tt/27C corner prose
- **Issue #75** (closed): Kickback evidence writer hardcodes 'tt/27C' corner prose into every non-tt record it writes

### 2026-10-03

- **PR #120**: chore(sim): remove dead ratified_oat_grid and unused measure.py surface
- **Issue #70** (closed): Remove port-ahead dead harness code: run_klt_yield(), ratified_oat_grid(), PROCESS_CORNERS

### 2026-10-02

- **PR #119**: feat: classify decision polarity and bisect decision-referred offset
- **PR #118**: docs: correct stale no-schematic claims in sim/harness docstrings
- **Issue #99** (closed): Two sim/harness docstrings still claim 'there is no comparator schematic yet' — design/comparator.sch landed in #25
- **Issue #66** (closed): sim: quantify the layout-induced systematic offset and the sub-20 mV decision-polarity asymmetry post-layout surfaced

### 2026-09-30

- **PR #117**: docs: embed fleet burndown chart in README
- **PR #62**: chore: retire the loom-workspace package.json stubs, alias to sim/selftest.sh
- **Issue #58** (closed): Retire the uncustomized loom-workspace package.json stubs: npm test/check:ci exit 0 without running the real gates
- **Issue #42** (closed): README: embed the fleet burndown chart (one line)

### 2026-09-27

- **PR #116**: docs: state integrator-view null-accepting rule as standing, not current-state
- **Issue #115** (closed): Three prose sites still say the integrator view's gds/measured_area are null because no layout exists — layout landed in #45
- **PR #114**: refactor: single-source the selftest fixture skeleton and star-leg assertion
- **PR #113**: refactor: single-source the --check-env reporting block in toolchain.py
- **PR #112**: refactor: replace hand-rolled probit bisection with statistics.NormalDist
- **PR #111**: ci: run full sim/tests unit suite instead of test_extract_pex.py filter
- **Issue #110** (closed): Deduplicate two copy-pasted test-support bodies that have already drifted
- **PR #109**: fix: widen T1 item 8's freshness guard to cover non-record row-table citations
- **Issue #108** (closed): Consolidate the duplicated --check-env reporting block: run.py's copy has already drifted from harness/cli.py's
- **PR #107**: docs: --chunk-decks counts campaign decks, not 'Monte Carlo decks' (#104)
- **Issue #106** (closed): Replace the hand-rolled probit bisection with statistics.NormalDist and drop its duplicated inline re-derivation
- **Issue #105** (closed): CI runs 22 of the 159 unit tests: the -p test_extract_pex.py filter narrows a suite that is already hermetic
- **Issue #104** (closed): noise-tran --chunk-decks counts every campaign deck, not the 'Monte Carlo decks' its help and README claim
- **Issue #102** (closed): T1 item 8's freshness guard claims to pin every row-table citation but only checks evidence records

### 2026-09-26

- **PR #103**: feat: add a chunked, resumable noise-tran runner for full-N campaigns
- **PR #101**: sim: post-layout noise-tran at sf/-40C, sf/125C and fs/-40C -- the last three graded corners (#95)
- **Issue #100** (closed): sim: build a resumable/chunked noise-tran runner so full-N post-layout re-runs fit the ~60-minute command ceiling
- **PR #98**: docs: aggregate #88's four post-layout offset corners into the characterization report (5 of 5 _mm)
- **PR #97**: chore: replace description=__doc__ with purpose-written one-liners at two CLI entry points
- **PR #96**: sim: post-layout noise-tran at ss/-40C and ff/125C, plus the SCHEMATIC_BASELINES entry gap that blocked both
- **Issue #95** (closed): sim: the three counterpart-less post-layout noise-tran corners, and the full-N re-runs the ~60-minute command ceiling blocks
- **Issue #94** (closed): Remove description=__doc__ from two entry points: --help reprints the whole module docstring as one re-wrapped paragraph
- **PR #93**: scripts: drop the unused Counter import from the device-count gate
- **Issue #92** (closed): Remove unused Counter import in scripts/check-layout-device-count.py
- **Issue #91** (closed): docs: sim/characterization-report.md is stale for #88's four post-layout offset records (row 1 still says 1 of 5)
- **PR #90**: sim: post-layout noise-tran at fs/125C closes DR-006's compliance basis
- **Issue #89** (closed): sim: post-layout noise-tran at the five remaining graded corners, plus the BASELINES entry gap #83 found
- **PR #88**: sim: post-layout offset campaign at the four remaining _mm mismatch corners
- **PR #87**: docs: aggregate the characterization report and cite it for T1 item 8 (generic evidence envelope)
- **Issue #86** (closed): docs: aggregate the characterization report and cite it for T1 item 8 (generic evidence envelope)
- **PR #85**: sim: consolidate the record-setup preamble in run.py's evidence writers
- **PR #84**: docs: correct sim/README.md's stale placeholder-DUT claim
- **Issue #83** (closed): sim: post-layout noise-tran at fs/125C (DR-006's closure condition) and the remaining graded corners
- **Issue #80** (closed): sim: post-layout offset campaign at the four remaining _mm mismatch corners
- **Issue #79** (closed): Consolidate duplicated record-setup preamble across the six write_*_evidence functions
- **Issue #78** (closed): sim/README.md still claims sim/comparator-decision/ exercises a placeholder DUT (superseded by issue #24)

### 2026-09-25

- **PR #82**: sim: give reset and noise-tran a post-layout deck form, and run both
- **PR #81**: sim: complete the post-layout PVT campaign across the graded corners
- **PR #77**: docs: drop stale bootstrap-era claims from sim/README.md
- **PR #76**: layout: klt erc supply-spec run for T1 item 11, committed and deliberately uncited
- **Issue #74** (closed): Remove stale bootstrap-era claims from sim/README.md (DRAFT spec, no schematic)
- **PR #73**: sim: qualify the ported sky130-sar-adc issue citations and drop two fictional call sites
- **PR #72**: scripts: finish the _gate_common extraction (selftest tally + main() dispatch tails)
- **Issue #71** (closed): Requalify the ported foreign issue citations in sim/: ten bare 'issue #N' refs point at another repo's tracker
- **Issue #69** (closed): Finish the _gate_common extraction: the selftest tally and main() dispatch tails are still duplicated across the gates
- **Issue #68** (closed): layout: klt erc supply-spec run + compound item-11 citation (T1 item 11, power delivery structural)
- **PR #67**: layout: post-layout (extracted-netlist) re-simulation for the comparator (T1 item 7)
- **Issue #65** (closed): sim: give reset and noise-tran a post-layout deck form (they currently refuse --dut extracted)
- **Issue #64** (closed): sim: complete the post-layout PVT campaign across the remaining graded corners (follow-on to T1 item 7)
- **PR #63**: tests: drop the shadowed duplicate test method in test_comparator_decision.py
- **PR #61**: manifests: make maturity_rung_basis checkable against the signoff report
- **PR #60**: scripts: extract the shared fail/ok/load_json CI-gate helpers into _gate_common.py
- **Issue #59** (closed): Remove the shadowed duplicate test method in sim/tests/test_comparator_decision.py: 1 of 34 tests never runs
- **Issue #57** (closed): layout: post-layout (extracted-netlist) re-simulation for the comparator (T1 item 7)
- **Issue #56** (closed): Extract shared fail/ok/load_json CI-gate helpers: check-integrator-view.py duplicates check-t1-signoff.py
- **PR #55**: layout: withdraw the T1 item-4 LVS citation — the match has the known delta in its blind spot
- **PR #54**: layout: commit the LVS signoff envelope and cite it for T1 item 4
- **PR #53**: sim: drop the never-called _run_ts_retry helper
- **Issue #52** (closed): Remove dead _run_ts_retry helper in comparator-decision/run.py
- **Issue #50** (closed): integrator-view: maturity_rung_basis still claims 0/11 T1 items met, and nothing checks it
- **Issue #49** (closed): layout: LVS-clean signoff citation for the comparator (T1 item 4)

### 2026-09-24

- **PR #51**: chore: bump the klt pin to 0.6.0 (+ klayout 0.30.10) and regrade the T1 record
- **PR #48**: layout: commit the DRC signoff envelope and cite it for T1 item 3
- **Issue #47** (closed): chore: bump the klt pin off 0.5.0 to pick up input_verified + citation.coverage
- **Issue #46** (closed): layout: DRC-clean signoff citation for the comparator (T1 item 3)

