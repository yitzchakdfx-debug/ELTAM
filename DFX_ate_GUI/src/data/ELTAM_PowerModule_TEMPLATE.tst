# =====================================================================
# ELTAM Power Module - DRAFT test sequence (TEMPLATE)
# =====================================================================
# Built from the existing SPREOS template + your 20-requirement spec.
# ALL numeric limits, voltages and channel numbers below are PLACEHOLDERS
# marked "TODO" - replace them with the real values from the UUT test
# document before running on hardware.
#
# Command vocabulary (verified against the code):
#   setvoltage <v>        - PS (SOURCE) output voltage      [req #3, #4]
#   setload <w>           - electronic load, constant power; 0 = off  [req #10]
#   relay <line> on|off   - discrete line / mode switch      [req #9]
#   setlogic on|off       - the bench's main logic relay     [req #9]
#   readchannel <n>       - measure; V or A chosen by "Unit" [req #6,#7,#8]
#   getid                 - comms check on all instruments
#   Delay <ms> / Log <txt> / Prompt <txt> / PromptYesNo <txt>
# Keywords: Critical | Limits <min> <max> | Target <v> Tol <%> | Unit V|A | Retry <n>
#
# TODO: set the real part number on the next line (no inline comment after it)
# PartNum: ELTAM-PWR-XXXX
# =====================================================================


# ---------------------------------------------------------------------
# Phase 0 - Safety init & communications (Critical: abort run on fail)
# ---------------------------------------------------------------------
:Init - Power Off and Comms Check
Critical
setvoltage 0.0
getid
Delay 300

:Operator - Insert UUT
Prompt Scan the UUT barcode, insert the board into the fixture, then click OK.
Log Operator confirmed UUT inserted.


# ---------------------------------------------------------------------
# req #3 - DC input range 9-33V : output rail must stay in spec
#          (No Load). readchannel 2 = output rail voltage tap (TODO: channel)
# ---------------------------------------------------------------------
:Input 9V (No Load) - Output Rail
setvoltage 9.0
Delay 500
Limits 4.90 5.10      # TODO: real output rail min/max
Unit V
readchannel 2

:Input 28V (No Load) - Output Rail
setvoltage 28.0
Delay 500
Limits 4.90 5.10      # TODO
Unit V
readchannel 2

:Input 33V (No Load) - Output Rail
setvoltage 33.0
Delay 500
Limits 4.90 5.10      # TODO
Unit V
readchannel 2


# ---------------------------------------------------------------------
# req #6/#7/#8 - read DC Voltage / Current / Power, nominal input
# Power (#8) is derived from a V reading and an A reading (V*A).
# ---------------------------------------------------------------------
:Nominal 28V - Output Voltage
setvoltage 28.0
Delay 300
Limits 4.90 5.10      # TODO
Unit V
readchannel 2

:Nominal 28V - Input Current (No Load)
Limits 0.0 0.50       # TODO: quiescent input current max
Unit A
readchannel 1         # channel 1 = SOURCE (PS) -> current because Unit A


# ---------------------------------------------------------------------
# req #10 - output load switching : apply electronic load, recheck rail
# ---------------------------------------------------------------------
:Apply 50W Load
Log Setting electronic load to 50W constant power.
setload 50.0          # TODO: real load point(s)
Delay 500

:Loaded - Output Rail Voltage
Limits 4.85 5.10      # TODO: loaded rail droop limits
Unit V
readchannel 2

:Loaded - Load Current
Limits 9.0 11.0       # TODO: expected load current at 50W
Unit A
readchannel 5         # channel 5 = LOAD -> current because Unit A

:Remove Load
setload 0.0
Delay 300


# ---------------------------------------------------------------------
# req #9 - operating-mode switching (discrete line / relay)
# ---------------------------------------------------------------------
:Enable Mode A
Log Switching UUT to operating Mode A.
relay 1 on            # TODO: which relay line = Mode A
Delay 300
Limits 4.90 5.10      # TODO: expected output in Mode A
Unit V
readchannel 2

:Disable Mode A
relay 1 off
Delay 200


# ---------------------------------------------------------------------
# req #11 - operator visual checks (PromptYesNo: Yes=PASS, No=FAIL)
# ---------------------------------------------------------------------
:Visual - Power LED ON
setvoltage 28.0
Delay 300
PromptYesNo Is the GREEN power LED lit steadily? (Yes = pass)

:Visual - Fault LED OFF
PromptYesNo Is the RED fault LED OFF? (Yes = pass)


# ---------------------------------------------------------------------
# Teardown - return to safe state
# ---------------------------------------------------------------------
:Cleanup
Log Test complete - returning to safe state.
setload 0.0
relay 1 off
setvoltage 0.0
Delay 300
