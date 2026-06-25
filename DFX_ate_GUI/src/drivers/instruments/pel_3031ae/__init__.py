"""GW Instek PEL-3031AE programmable DC electronic load.

Capability: ElectronicLoad (the bench LOAD role). Real driver over VISA plus a
Qt-free mock for Simulation. The PEL-3000(H) series speaks IEEE488.2/SCPI; over
USB it enumerates as a USB-CDC virtual COM (addressable as an ``ASRL`` VISA
resource), with optional GPIB/LAN.
"""
