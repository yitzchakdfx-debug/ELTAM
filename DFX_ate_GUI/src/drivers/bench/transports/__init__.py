"""Transport wrappers (VISA, serial, ...) shared by instrument drivers.

Each transport guards its optional third-party import so the package imports
cleanly with no comms stack installed; availability is reported via a helper
(e.g. `visa.visa_available()`) that the Sim/HW gate checks. Drivers own the
protocol; transports only manage the session and map faults to the project's
`HardwareError` hierarchy.
"""
