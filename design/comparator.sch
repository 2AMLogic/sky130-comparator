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

11 devices, exactly the DR-001 device set:
  1 tail switch NMOS              M_TAIL
  2 input-pair NMOS               M_INN, M_INP
  2 cross-coupled latch NMOS      M_LATN_P, M_LATN_N
  2 cross-coupled latch PMOS      M_LATP_P, M_LATP_N
  2 output-node reset PMOS        M_RST_P,  M_RST_N
  2 internal-node reset PMOS      M_RST_DIP, M_RST_DIN

Reset (CLK=0): all four reset PMOS conduct, precharging BOTH the differential
output nodes (OUTP/OUTN) AND the cross-coupled latch NMOS pair's own source
nodes (DIP/DIN) to VDD.  Every latch NMOS then sits at Vgs = 0 exactly (gate
at VDD from the opposite precharged output, source at VDD from its own
precharged internal node), so the positive-feedback loop's gain is zero and
the reset state is a stable, all-devices-off equilibrium with no VDD->GND
path -- DR-001 Decision 3.  This is the property the reset-integrity negative
control (sim/comparator-decision/run.py reset) exists to verify.

Evaluate (CLK=VDD): reset PMOS off, tail switch on; the input pair discharges
DIP/DIN at rates set by VINN/VINP, the latch NMOS pair's sources fall, the
loop gain rises through unity and the pair regenerates to the rails.

Ports (flat, top level -- drop-in DUT fragment for
sim/comparator-decision/testbench/comparator_core.spice):
  VDD, GND, CLK, VINP, VINN, OUTP, OUTN.     Internal nodes: TAIL, DIP, DIN.
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
                                            total W = 116 um

L = 0.5um, common to all 11 devices.  Not minimum L (0.15um): Pelgrom matching
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

C {lab_wire.sym} 20 -30 0 0 {name=l_tail_d lab=TAIL}
C {lab_wire.sym} -20 0 0 0 {name=l_tail_g lab=CLK}
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
C {lab_wire.sym} 130 200 0 0 {name=l_rstdip_g lab=CLK}
C {lab_wire.sym} 170 170 0 0 {name=l_rstdip_s lab=VDD}
C {lab_wire.sym} 170 200 0 0 {name=l_rstdip_b lab=VDD}

C {lab_wire.sym} 320 230 0 0 {name=l_rstdin_d lab=DIN}
C {lab_wire.sym} 280 200 0 0 {name=l_rstdin_g lab=CLK}
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
C {lab_wire.sym} 730 200 0 0 {name=l_rstp_g lab=CLK}
C {lab_wire.sym} 770 170 0 0 {name=l_rstp_s lab=VDD}
C {lab_wire.sym} 770 200 0 0 {name=l_rstp_b lab=VDD}

C {lab_wire.sym} 920 230 0 0 {name=l_rstn_d lab=OUTN}
C {lab_wire.sym} 880 200 0 0 {name=l_rstn_g lab=CLK}
C {lab_wire.sym} 920 170 0 0 {name=l_rstn_s lab=VDD}
C {lab_wire.sym} 920 200 0 0 {name=l_rstn_b lab=VDD}
