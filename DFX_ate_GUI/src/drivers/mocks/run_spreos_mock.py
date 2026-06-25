"""Qt-free harness: run the SPREOS test program against its mock driver.

Parses `SPREOS Power Supply Main Card Fix.tst`, drives every step through
:class:`SpreosPowerSupplyMock`, and applies the same PASS/FAIL logic the real
runner uses (`TestRunnerThread._run_step`) — without Qt, the database, or the
GUI. Use it to confirm the mock makes the test pass most of the time and fail
occasionally.

Run it:

    python src/drivers/mocks/run_spreos_mock.py            # one run
    python src/drivers/mocks/run_spreos_mock.py --runs 8   # show pass/fail spread
    python src/drivers/mocks/run_spreos_mock.py --seed 1   # reproducible
    python src/drivers/mocks/run_spreos_mock.py --fail-prob 0.4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python src/drivers/mocks/run_spreos_mock.py` (add <repo>/src to path).
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from drivers.mocks.spreos_power_supply_mock import SpreosPowerSupplyMock  # noqa: E402
from logic.models import TestStep  # noqa: E402
from logic.script_manager import ScriptManager  # noqa: E402

_DEFAULT_SCRIPT = _SRC / "data" / "SPREOS Power Supply Main Card Fix.tst"

# Commands the real runner services itself; they never reach the driver.
_RUNNER_SIDE = frozenset({"delay", "log", "prompt", "promptyesno"})


def _evaluate_step(
    step: TestStep, mock: SpreosPowerSupplyMock, *, answer_yes: bool
) -> tuple[bool, float | None]:
    """Mirror TestRunnerThread._run_step for one step: returns (passed, value)."""
    mock.set_active_step(step.unit, step.min_val, step.max_val)
    last: float | None = None
    has_yesno = False

    for cmd in step.commands:
        name = str(cmd["cmd"]).lower()
        args = cmd["args"]
        if name == "promptyesno":
            has_yesno = True
            last = 1.0 if answer_yes else 0.0
            continue
        if name in _RUNNER_SIDE:
            continue
        value = mock.execute_command(name, args)
        if name in mock.measurement_commands:
            last = value

    if step.has_limits:
        if last is None:
            return False, None
        assert step.min_val is not None and step.max_val is not None
        return step.min_val <= last <= step.max_val, last
    if has_yesno and last is not None:
        return last > 0.5, last
    return True, last


def run_once(
    script_path: Path, *, seed: int | None, fail_prob: float | None, answer_yes: bool
) -> bool:
    steps = ScriptManager().load_script(script_path)
    mock = SpreosPowerSupplyMock(fail_prob=fail_prob, seed=seed)
    mock.connect()

    overall = True
    try:
        for step in steps:
            passed, value = _evaluate_step(step, mock, answer_yes=answer_yes)
            if not passed:
                overall = False

            tag = "PASS" if passed else "FAIL"
            if step.has_limits:
                detail = (
                    f"value={value:.3f} {step.unit}".rstrip()
                    + f"  limits=[{step.min_val:g}, {step.max_val:g}]"
                )
            else:
                detail = "(setup/teardown - no measurement)"
            print(f"  [{tag}] {step.name}: {detail}")

            if step.is_critical and not passed:
                print("  >>> CRITICAL step failed — runner would abort here.")
                break
    finally:
        mock.disconnect()

    print(f"  OVERALL: {'PASS' if overall else 'FAIL'}")
    return overall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", nargs="?", type=Path, default=_DEFAULT_SCRIPT)
    parser.add_argument("--runs", type=int, default=1, help="number of full runs")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (reproducible)")
    parser.add_argument(
        "--fail-prob", type=float, default=None,
        help="per-measurement out-of-spec probability (default: the mock's own, 0.02)",
    )
    parser.add_argument(
        "--answer-no", action="store_true",
        help="answer the LED PromptYesNo steps with No (they then FAIL)",
    )
    args = parser.parse_args(argv)

    if not args.script.is_file():
        parser.error(f"script not found: {args.script}")

    fail_prob = args.fail_prob  # None -> SpreosPowerSupplyMock uses its own default
    passes = 0
    for i in range(1, args.runs + 1):
        print(f"\n=== Run {i}/{args.runs} ===")
        # Vary the seed per run so a fixed --seed is still reproducible overall.
        seed = None if args.seed is None else args.seed + i
        if run_once(
            args.script, seed=seed, fail_prob=fail_prob, answer_yes=not args.answer_no
        ):
            passes += 1

    print(f"\nSummary: {passes}/{args.runs} run(s) passed overall.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
