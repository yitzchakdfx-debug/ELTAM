"""Test-specific mock drivers.

Unlike the generic, stateless :class:`drivers.mock_hardware.MockHardware`,
each module here simulates the *instrument set for one concrete `.tst` test
program*. The mock tracks the state set by side-effect commands
(`setvoltage`, `setlogic`, `setload`, ...) so that `readchannel` returns
physically plausible per-channel values — passing most of the time and
failing occasionally.

These are stand-ins used to exercise the app end-to-end until the real
instrument drivers are connected. When real hardware arrives, write a
`BaseDriver` subclass for it and pass it via `TestRunnerThread(driver=...)`;
the channel map will differ (see each mock's module docstring).
"""

from drivers.mocks.spreos_power_supply_mock import SpreosPowerSupplyMock

__all__ = ["SpreosPowerSupplyMock"]
