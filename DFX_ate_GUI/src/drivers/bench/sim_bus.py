"""Shared electrical state for a *coupled* bench simulation.

In Simulation mode the three SPREOS instrument mocks share one `SimBus` so a
`setvoltage` on the PS is reflected in the DAQ voltage taps and the load's
readings — closing the gap where independent mocks drifted apart. The bench
factory creates the bus and injects it into each mock (`bus=...`); standalone
(unit-test) construction leaves `bus=None` and keeps the mocks' isolated logic.

Qt-free, no DB, no I/O.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class SimBus:
    """The bench's shared electrical state."""

    input_voltage: float = 0.0   # PS rail, set by `setvoltage`
    load_watts: float = 0.0      # electronic-load constant power, set by `setload`
    logic_on: bool = False       # logic-power discrete line, set by `setlogic`


def reading(
    rng: random.Random,
    nominal: float,
    *,
    jitter: float = 0.1,
    fail_prob: float = 0.0,
    fail_kick: float = 0.8,
) -> float:
    """A simulated measurement: nominal + small jitter, occasionally out of spec.

    With probability `fail_prob` the value is kicked well past the usual jitter
    band (so it tends to fall outside a typical limit window), reproducing the
    "mostly pass, sometimes fail" behavior of the original bench mock without the
    reader needing to know the step's limits.
    """
    if fail_prob and rng.random() < fail_prob:
        sign = 1.0 if rng.random() < 0.5 else -1.0
        return round(nominal + sign * (fail_kick + rng.uniform(0.0, 0.4)), 4)
    return round(nominal + rng.uniform(-jitter, jitter), 4)
