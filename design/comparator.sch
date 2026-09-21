v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {sky130-comparator -- design/comparator.sch  (issue #24)

Single-tail, bottom-tail NMOS-input dynamic latch. No static preamp.
Topology and reset scheme per spec/decision-records/DR-001-comparator-topology.md
(issue #21 / PR #22); this schematic implements that decision, it does not
re-open it.

13 devices -- the 11-device DR-001 set plus the 2-device slew-shaper
DR-003 (issue #30, kickback mitigation) hangs off the clock port:
  1 tail switch NMOS         M_TAIL              (gate at CLKT, see below)
  2 input-pair NMOS          M_INN, M_INP
  2 cross-coupled latch NMOS M_LATN_P, M_LATN_N
  2 cross-coupled latch PMOS M_LATP_P, M_LATP_N
  2 output-node reset PMOS   M_RST_P,  M_RST_N       (gates at CLKT)
  2 internal-node reset PMOS M_RST_DIP, M_RST_DIN     (gates at CLKT)
  1 poly clock resistor      R_CLKS   (CLK -> CLKT, res_high_po)
  1 clock MOS capacitor      M_CLKCAP (CLKT -> GND, nfet_01v8)

Reset (CLK=0): all four reset PMOS conduct, precharging BOTH the differential
output nodes (OUTP/OUTN) AND the cross-coupled latch NMOS pair's own source
nodes (DIP/DIN) to VDD.  Every latch NMOS then sits at Vgs = 0 exactly (gate
at VDD from the opposite precharged output, source at VDD from its own
precharged internal node), so the positive-feedback loop's gain is zero and
the reset state is a stable, all-devices-off equilibrium with no VDD->GND
path -- DR-001 Decision 3.  This is the property the reset-integrity negative
control (sim/comparator-decision/run.py reset) exists to verify.

Evaluate (CLK rising): the soft-clock network R_CLKS + M_CLKCAP forms the
internal node CLKT (tau ~ 250 ps), and ALL five clocked gates -- the tail
switch and the four reset PMOS -- are driven by CLKT, not by CLK itself.
The whole evaluate onset (precharge release + tail turn-on together) is
therefore slew-limited to that RC rather than to the testbench's 100 ps
ramp: the DIP/DIN collapse that couples through the input pair's Cgd into
VINP/VINN is stretched, and the peak input disturbance falls with it.
Reset (CLK low) rests identically to DR-001's scheme: CLKT discharges to
GND through R_CLKS, so every gate sits exactly where the DR-001 design put
it -- the reset-integrity property is unchanged, and only the TRANSITION
is shaped.  See the DR-003 block below for why this, and not the other
candidate mitigations, is what this schematic carries.

Ports (flat, top level -- drop-in DUT fragment for
sim/comparator-decision/testbench/comparator_core.spice):
  VDD, GND, CLK, VINP, VINN, OUTP, OUTN.     Internal nodes: TAIL, DIP,
  DIN, CLKT.
Polarity: Vin,diff = VINP - VINN > 0  =>  OUTP settles high.
  (VINP drives M_INP, whose drain is DIN; DIN falls faster, M_LATN_N turns on
   first and pulls OUTN down, leaving OUTP at VDD.)

Every device is sky130_fd_pr__{n,p}fet_01v8 -- the 1.8V core flavour, the only
complementary pair sky130 ships (top-level README, "Supply / power" row) and
the flavour this repo's 1.8V headroom constraint (CLAUDE.md) refers to.} -60 -980 0 0 0.35 0.35 {}

T {SIZING RATIONALE (issue #24) -- derived first-principles against this repo's
own installed sky130 device models, NOT scaled from the sim/comparator-decision
placeholder DUT.  Full derivation, evidence and corner data: DR-001 Amendment 1
(spec/decision-records/DR-001-comparator-topology.md) and the supporting decks
under spec/dr-001-support/.

  Device group          Devices                 W (um)  L (um)   set by
  --------------------  ----------------------  ------  ------   ----------------
  tail switch           M_TAIL                    20     0.5     headroom (Ron)
  input pair            M_INN, M_INP              10     0.5     offset budget
  cross-coupled NMOS    M_LATN_P, M_LATN_N         8     0.5     offset budget
  cross-coupled PMOS    M_LATP_P, M_LATP_N        16     0.5     trip point
  output reset PMOS     M_RST_P, M_RST_N           8     0.5     reset tau / C_out
  internal reset PMOS   M_RST_DIP, M_RST_DIN       6     0.5     reset tau / C_DI
  clock shaper R        R_CLKS                    --    1.75    kickback (DR-003)
  clock shaper C        M_CLKCAP                  20     0.5     kickback (DR-003)
                                            total W = 136.15 um

L = 0.5um, common to all 12 MOSFETs.  Not minimum L (0.15um): Pelgrom matching
improves as 1/sqrt(W*L), so L is the cheaper of the two area axes for the
offset-critical devices (it costs gm linearly but buys matching as sqrt(L)),
and at 0.15um the DIBL-driven output conductance degrades the cross-coupled
pair's small-signal loop gain, which is what sets the regeneration time
constant.  A single common L keeps every device group on the same
matching/speed footing and on one poly-pitch family for future layout.
L = 0.5um is also DR-001's own probe geometry, so that record's four-corner
Vth/Vdsat table transfers to these devices directly.

W_in = 10um -- set by the OFFSET BUDGET, from this PDK's own mismatch model.
The only local-mismatch (MC_MM_SWITCH) term either 01v8 flavour carries is a
delvto shift, sigma = AVT/sqrt(W*L*mult), with the AVT coefficients read
straight out of the installed model library
(libs.tech/combined/continuous/models_global.spice):
    AVT_n = sw_mm_vth0_sky130_fd_pr__nfet_01v8 = 3.356 mV.um
    AVT_p = sw_mm_vth0_sky130_fd_pr__pfet_01v8 = 5.856 mV.um
(the companion deltox / beta-mismatch line is COMMENTED OUT in both device
subcircuits -- on this PDK, local mismatch is threshold mismatch only.  This
is confirmed empirically in spec/dr-001-support/avt_probe.spice.)
For a differential pair the pair-referred sigma is sqrt(2) x the single-device
value.  Budgeting 70% of the offset VARIANCE to the input pair against the
top-level README's DRAFT stretch row (3 sigma <= 8 mV, i.e. sigma <= 2.667 mV):
    W_in*L_in  >=  2*AVT_n^2 / (0.7 * (8/3)^2)  =  4.53 um^2
    -> W_in >= 9.05um at L = 0.5um    -> chosen W_in = 10um
       (input-pair contribution sigma = 3.356*sqrt(2/5) = 2.12 mV)

W_latn = 8um -- the second offset contributor.  The latch NMOS pair's own Vth
mismatch is referred to the input divided by the input pair's integration gain,
so it needs area but less of it than the input pair; 8um spends the remaining
30% of the variance budget.  It must also be strong enough that regeneration,
once DIP/DIN have fallen, is driven by the cross-coupled pair rather than the
input pair.

W_latp = 16um = 2 x W_latn -- sky130's mobility ratio at this node is
mu_n/mu_p ~ 2, so W_p = 2*W_n puts the cross-coupled inverter's trip point near
VDD/2.  That is the symmetric point: it maximises the regenerative loop gain at
the moment the loop closes and minimises the latch's own systematic offset.

W_tail = 20um = 2 x W_in -- set by HEADROOM, not by matching.  The tail's own
Vth mismatch is a common-mode perturbation (it moves both branch currents
equally) and does not appear in the input-referred offset to first order.  Its
gate is driven by CLK FULL SWING, so it is a switch in deep triode, not a
saturated current source: its only sizing requirement is that its Ron drop
V(TAIL) stay a small fraction of the 1.8V headroom budget at the worst corner.
2 x the input-pair width achieves that -- see DR-001 Amendment 1 for the
four-corner self-consistent .op evidence, including the ss/-40C point DR-001
flagged as a -58.5 mV deficit under its planning convention.

W_rst_out = 8um, W_rst_int = 6um -- deliberately SMALLER, relative to the latch
devices, than the placeholder DUT's proportions.  During reset the latch NMOS
are held fully off by the DIP/DIN precharge, so the reset PMOS have only node
capacitance to charge: with Ron*W ~ 6 kohm.um for this pfet at full drive and
C_out of order 100 fF, tau is well under 100 ps against a 5 ns reset window --
two orders of margin.  Reset speed is therefore NOT the binding constraint;
the reset devices' own drain junction capacitance, which sits directly on
OUTP/OUTN and DIP/DIN and slows regeneration, is.  So they are sized down to
the smallest value that still keeps that margin comfortable.} -60 -680 0 0 0.28 0.28 {}

C {sky130_fd_pr/nfet_01v8.sym} 0 0 0 0 {name=M_TAIL L=0.5 W=20 nf=1 model=nfet_01v8}
C {sky130_fd_pr/nfet_01v8.sym} 150 0 0 0 {name=M_INN L=0.5 W=10 nf=1 model=nfet_01v8}
C {sky130_fd_pr/nfet_01v8.sym} 300 0 0 0 {name=M_INP L=0.5 W=10 nf=1 model=nfet_01v8}
C {sky130_fd_pr/nfet_01v8.sym} 450 0 0 0 {name=M_LATN_P L=0.5 W=8 nf=1 model=nfet_01v8}
C {sky130_fd_pr/nfet_01v8.sym} 600 0 0 0 {name=M_LATN_N L=0.5 W=8 nf=1 model=nfet_01v8}

C {sky130_fd_pr/pfet_01v8.sym} 150 200 0 0 {name=M_RST_DIP L=0.5 W=6 nf=1 model=pfet_01v8}
C {sky130_fd_pr/pfet_01v8.sym} 300 200 0 0 {name=M_RST_DIN L=0.5 W=6 nf=1 model=pfet_01v8}
C {sky130_fd_pr/pfet_01v8.sym} 450 200 0 0 {name=M_LATP_P L=0.5 W=16 nf=1 model=pfet_01v8}
C {sky130_fd_pr/pfet_01v8.sym} 600 200 0 0 {name=M_LATP_N L=0.5 W=16 nf=1 model=pfet_01v8}
C {sky130_fd_pr/pfet_01v8.sym} 750 200 0 0 {name=M_RST_P L=0.5 W=8 nf=1 model=pfet_01v8}
C {sky130_fd_pr/pfet_01v8.sym} 900 200 0 0 {name=M_RST_N L=0.5 W=8 nf=1 model=pfet_01v8}
C {sky130_fd_pr/res_high_po_0p35.sym} 0 -150 0 0 {name=R_CLKS L=1.75 mult=1 model=res_high_po_0p35 spiceprefix=X}
C {lab_wire.sym} 0 -120 0 0 {name=l_clks_p lab=CLKT}
C {lab_wire.sym} -20 -150 0 0 {name=l_clks_b lab=GND}
C {lab_wire.sym} 0 -180 0 0 {name=l_clks_m lab=CLK}
C {sky130_fd_pr/nfet_01v8.sym} 150 -150 0 0 {name=M_CLKCAP L=0.5 W=20 nf=1 model=nfet_01v8}
C {lab_wire.sym} 170 -180 0 0 {name=l_clkcap_d lab=GND}
C {lab_wire.sym} 130 -150 0 0 {name=l_clkcap_g lab=CLKT}
C {lab_wire.sym} 170 -120 0 0 {name=l_clkcap_s lab=GND}
C {lab_wire.sym} 170 -150 0 0 {name=l_clkcap_b lab=GND}

C {lab_wire.sym} 20 -30 0 0 {name=l_tail_d lab=TAIL}
C {lab_wire.sym} -20 0 0 0 {name=l_tail_g lab=CLKT}
C {lab_wire.sym} 20 30 0 0 {name=l_tail_s lab=GND}
C {lab_wire.sym} 20 0 0 0 {name=l_tail_b lab=GND}

C {lab_wire.sym} 170 -30 0 0 {name=l_inn_d lab=DIP}
C {lab_wire.sym} 130 0 0 0 {name=l_inn_g lab=VINN}
C {lab_wire.sym} 170 30 0 0 {name=l_inn_s lab=TAIL}
C {lab_wire.sym} 170 0 0 0 {name=l_inn_b lab=GND}

C {lab_wire.sym} 320 -30 0 0 {name=l_inp_d lab=DIN}
C {lab_wire.sym} 280 0 0 0 {name=l_inp_g lab=VINP}
C {lab_wire.sym} 320 30 0 0 {name=l_inp_s lab=TAIL}
C {lab_wire.sym} 320 0 0 0 {name=l_inp_b lab=GND}

C {lab_wire.sym} 470 -30 0 0 {name=l_latnp_d lab=OUTP}
C {lab_wire.sym} 430 0 0 0 {name=l_latnp_g lab=OUTN}
C {lab_wire.sym} 470 30 0 0 {name=l_latnp_s lab=DIP}
C {lab_wire.sym} 470 0 0 0 {name=l_latnp_b lab=GND}

C {lab_wire.sym} 620 -30 0 0 {name=l_latnn_d lab=OUTN}
C {lab_wire.sym} 580 0 0 0 {name=l_latnn_g lab=OUTP}
C {lab_wire.sym} 620 30 0 0 {name=l_latnn_s lab=DIN}
C {lab_wire.sym} 620 0 0 0 {name=l_latnn_b lab=GND}

C {lab_wire.sym} 170 230 0 0 {name=l_rstdip_d lab=DIP}
C {lab_wire.sym} 130 200 0 0 {name=l_rstdip_g lab=CLKT}
C {lab_wire.sym} 170 170 0 0 {name=l_rstdip_s lab=VDD}
C {lab_wire.sym} 170 200 0 0 {name=l_rstdip_b lab=VDD}

C {lab_wire.sym} 320 230 0 0 {name=l_rstdin_d lab=DIN}
C {lab_wire.sym} 280 200 0 0 {name=l_rstdin_g lab=CLKT}
C {lab_wire.sym} 320 170 0 0 {name=l_rstdin_s lab=VDD}
C {lab_wire.sym} 320 200 0 0 {name=l_rstdin_b lab=VDD}

C {lab_wire.sym} 470 230 0 0 {name=l_latpp_d lab=OUTP}
C {lab_wire.sym} 430 200 0 0 {name=l_latpp_g lab=OUTN}
C {lab_wire.sym} 470 170 0 0 {name=l_latpp_s lab=VDD}
C {lab_wire.sym} 470 200 0 0 {name=l_latpp_b lab=VDD}

C {lab_wire.sym} 620 230 0 0 {name=l_latpn_d lab=OUTN}
C {lab_wire.sym} 580 200 0 0 {name=l_latpn_g lab=OUTP}
C {lab_wire.sym} 620 170 0 0 {name=l_latpn_s lab=VDD}
C {lab_wire.sym} 620 200 0 0 {name=l_latpn_b lab=VDD}

C {lab_wire.sym} 770 230 0 0 {name=l_rstp_d lab=OUTP}
C {lab_wire.sym} 730 200 0 0 {name=l_rstp_g lab=CLKT}
C {lab_wire.sym} 770 170 0 0 {name=l_rstp_s lab=VDD}
C {lab_wire.sym} 770 200 0 0 {name=l_rstp_b lab=VDD}

C {lab_wire.sym} 920 230 0 0 {name=l_rstn_d lab=OUTN}
C {lab_wire.sym} 880 200 0 0 {name=l_rstn_g lab=CLKT}
C {lab_wire.sym} 920 170 0 0 {name=l_rstn_s lab=VDD}
C {lab_wire.sym} 920 200 0 0 {name=l_rstn_b lab=VDD}
T {KICKBACK MITIGATION (issue #30, DR-003) -- a 2-device slew-shaper (poly
resistor R_CLKS + MOS capacitor M_CLKCAP) on the clock port: the internal
node CLKT drives ALL five clocked gates, stretching the evaluate onset.

The problem: DR-002 ratified the Kickback row (<= 5 mV disturbance into a
1 kOhm source impedance, stretch <= 2 mV, single decision edge) and measured
this design at 144.60 mV peak (sim/comparator-decision/records/
20260916-060139-f1eb978.md, tt/27C, 50 mV overdrive) -- ~29x the target.
Waveform decomposition of that measurement: the transition first kicks TAIL
upward through the tail switch's gate capacitance (+38 mV pin lobe via the
input pair's Cgs), then DIP/DIN -- precharged to VDD -- collapse through the
input pair, the fast first phase of that collapse driving a -145 uA
displacement spike into each pin through the input device's own Cgd, with
the peak arriving right at the END of the 100 ps CLK ramp.

What makes 5 mV hard here: the dominant charge keeps flowing past the end
of the ramp, so every CLK-correlated compensation is mistimed; and the
collapse rate is set by the tail switch + input pair conductance, so any
rate-based reduction trades roughly 1:1 into decision time.  Measured
candidates, all against this exact design (scratch-deck series, tt/27C
unless noted; full table in DR-003):

  - Reset-switch resizing (M_RST_DIP/DIN 6 um, M_RST_P/N 8 um, all -> 1 um):
    the spike is UNCHANGED (-146 mV) -- reset PMOS channel injection is not
    the mechanism.
  - Input-pair shrink (W_in 10 -> 5 um): kickback tracks roughly W
    (-93 mV); 29x is unreachable without destroying the ratified offset
    row's matching budget (sigma ~ 1/sqrt(W*L)).
  - Feedthrough-cancellation caps CLK->VINP/VINN: 4 fF leaves -104 mV,
    8 fF overshoots to +166 mV -- no value cancels both lobes because the
    trailing charge arrives after the compensation ends.  It would also
    re-inject on every falling edge of every later cycle.
  - Input isolation switches (4-deep min-width always-on NMOS stack per
    side, W = 0.42 um): the pin DISTURBANCE met the bound (-2.71 mV @ tt,
    -3.67 @ ff/125C, -1.65 @ ss/-40C) but the design was REJECTED on two
    measured regressions: (a) regeneration time 0.68 -> 3.80 ns @ 50 mV
    (the chain's ~RC hangover suppresses the input pair's Vgs during the
    decision edge, and the 3-deep variant breaches the 5 mV bound at
    ff/125C: -5.10 mV), and (b) the RATIFIED Input-referred-noise row's
    own methodology (loop-broken sub-model, input referred over
    1 kHz-1 GHz through the ideal AC source) measures 17.53 mV
    differential through the chain's ~132 MHz input pole, vs the ratified
    <= 1 mV bound and the pre-mitigation 0.4466 mV -- a regression the
    issue's no-regression acceptance criterion excludes outright.

The chosen mechanism -- direction 3 of DR-002's candidate list
(bootstrapped/slew-limited clocking), applied to the WHOLE evaluate onset:
R_CLKS (res_high_po_0p35, L = 1.75 um, ~2.4 kOhm) from CLK to CLKT, and
M_CLKCAP (nfet_01v8, W = 20 um, L = 0.5 um, ~100 fF, gate at CLKT, all
other terminals at GND) clamp CLKT, giving tau ~ 0.25 ns; the five clocked
gates (M_TAIL, M_RST_DIP, M_RST_DIN, M_RST_P, M_RST_N) all moved from CLK
to CLKT, so precharge release and tail turn-on slew TOGETHER.  Softening
both halves of the onset removes the reset-channel-injection overshoot of
DIP/DIN (their rise above VDD before collapse) and slows the collision
that lags it.  Probe-measured, same deck shape as the graded one:

    peak |VIN-pin disturbance|     regen @ 50 mV   (probe refs)
    tt/27C   -85.2 mV (-41%)         1.18 ns   (pre: 144.6 mV / 0.68 ns)
    ss/-40C  -79.8                   1.19 ns
    ff/125C  -86.4                   1.17 ns   (all < the DRAFT row's
                                                1.5 ns target)

What this design does NOT claim: full compliance.  The ratified <= 5 mV
bound is still missed by ~17x; the stretch bound further.  The measured
candidates above bound what the DR-001 topology (single-tail dynamic
latch, no static preamp, 7 flat ports) can reach without regressing a
ratified row; the ~1:1 rate/decision-time elasticity and the isolation
chain's noise-pole failure mean closing the remaining gap requires the
topology class DR-001 explicitly scoped OUT (a preamplifier or double-tail
isolation in front of the latch) -- follow-on work, named in DR-003 with
these numbers.

Consequences stated plainly: the shaped transition opens a ~250 ps window
where the tail sinks while the precharge PMOS are not yet fully off
(brief contention current, unmeasured -- the Supply/power row is open);
tau drifts with PVT (R and C each ~ +/-15-20%), so the trade floats with
it -- the probe matrix above brackets that spread.  The noise and offset
methodologies see no structural change: the noise sub-model re-emits the
tail with its gate on the steady CLKT node (see run.py), and the offset/
regen benches drive CLK from ideal sources exactly as before.

Full decision record: spec/decision-records/DR-003-kickback-slew-limited-clock.md
Post-mitigation evidence: sim/comparator-decision/records/ (kickback re-run,
offset/noise regressions) -- issue #30.} -60 -1520 0 0 0.28 0.28 {}
