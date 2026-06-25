"""Background test sequencer (QThread).

Loads a `.tst` script via `ScriptManager`, walks each `TestStep`, dispatches
hardware commands through `MockHardware.execute_command`, applies inline
limits, retries failing steps as configured, and aborts the run when a
`Critical` step fails. `Prompt` parks the runner on a `threading.Event`
that the UI releases via `resume()`. UI-free except for Qt threading
primitives and the standard-library `Event`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal

from drivers.base_driver import BaseDriver, HardwareError
from drivers.mock_hardware import MockHardware
from logic.database_manager import DatabaseManager
from logic.models import TestResultPayload, TestRunRecord, TestStep
from logic.script_manager import ScriptManager, ScriptParseError
from logic.secure_logger import get_secure_logger


class TestRunnerThread(QThread):
    """Runs a parsed `.tst` script off the GUI thread; reports via signals."""

    log_msg = Signal(str)
    test_result = Signal(str, dict)
    progress_total = Signal(int)
    progress_test = Signal(int)
    current_test = Signal(str)
    prompt_request = Signal(str)
    prompt_yesno_request = Signal(str)
    script_log = Signal(str)
    # Emitted at the start of each loop iteration (1-based) when loop_count > 1.
    loop_started = Signal(int, int)

    def __init__(
        self,
        script_path: Path,
        selected_names: set[str],
        *,
        loop_count: int = 1,
        stop_on_fail: bool = False,
        operator: str = "",
        tester_name: str = "",
        employee_id: str = "",
        uut_type: str = "",
        part_number: str = "",
        serial_number: str = "",
        script_manager: ScriptManager | None = None,
        start_time: datetime | None = None,
        logical_script_name: str = "",
        driver: BaseDriver | None = None,
    ) -> None:
        super().__init__()
        self._script_path = Path(script_path)
        self._logical_script_name = logical_script_name.strip() or self._script_path.stem
        self._selected_names = set(selected_names)
        self._loop_count = max(1, loop_count)
        self._stop_on_fail = stop_on_fail
        self._script_manager = script_manager or ScriptManager()
        self._hw: BaseDriver = driver or MockHardware()
        self._stop_requested = False
        self._prompt_event: Event = Event()
        self._yesno_event: Event = Event()
        self._yesno_answer: bool = False
        self._pause_event: Event = Event()
        self._pause_event.set()  # set = running; clear = paused
        self._db = DatabaseManager()
        try:
            self._secure_log = get_secure_logger()
        except Exception:
            self._secure_log = None
        self.tester_name = tester_name.strip() or operator.strip()
        self.employee_id = employee_id.strip()
        self.uut_type = uut_type.strip()
        self._start_dt = start_time or datetime.now()
        self._run_record = TestRunRecord(
            operator=operator.strip() or self.tester_name,
            part_number=part_number,
            serial_number=serial_number,
            overall_passed=True,
            start_time=self._start_dt,
        )

    def _emit_log(self, category: str, msg: str) -> None:
        self.log_msg.emit(msg)
        if self._secure_log is not None:
            try:
                self._secure_log.log(
                    "trace",
                    {
                        "category": category,
                        "message": msg,
                        "script": self._logical_script_name,
                    },
                )
            except Exception:
                pass

    def run(self) -> None:
        self.progress_total.emit(0)
        self.progress_test.emit(0)
        self.current_test.emit("")

        overall_passed = True

        try:
            try:
                if not self._hw.connect():
                    self._emit_log("error", "Hardware connect() returned False; aborting.")
                    overall_passed = False
                    return
            except HardwareError as exc:
                self._emit_log("error", f"Hardware connection failed: {exc}")
                overall_passed = False
                return

            try:
                all_steps = self._script_manager.load_script(self._script_path)
            except ScriptParseError as exc:
                self._emit_log(
                    "error",
                    f"Script load failed at line {exc.line_no}: {exc.msg}",
                )
                overall_passed = False
                return
            except (OSError, ValueError) as exc:
                self._emit_log("error", f"Script load failed: {exc}")
                overall_passed = False
                return

            steps = [s for s in all_steps if s.name in self._selected_names]
            if not steps:
                self._emit_log("info", "No steps selected to run.")
                return

            total_steps = len(steps) * self._loop_count
            completed = 0
            abort_all_loops = False

            for _loop in range(self._loop_count):
                if self._stop_requested:
                    self._emit_log("info", "Test execution aborted by user.")
                    break

                loop_number = _loop + 1
                if self._loop_count > 1:
                    self.loop_started.emit(loop_number, self._loop_count)
                    self._emit_log(
                        "info",
                        f"--- Loop {loop_number}/{self._loop_count} ---",
                    )

                for step in steps:
                    self._pause_event.wait()
                    if self._stop_requested:
                        self._emit_log("info", "Test execution aborted by user.")
                        abort_all_loops = True
                        break

                    self.current_test.emit(step.name)
                    self.progress_test.emit(0)
                    self._emit_log(
                        "cmd",
                        f"Executing: {step.name}... "
                        f"[Script: {self._logical_script_name}]",
                    )

                    attempts_total = step.retry_count + 1
                    passed = False
                    value: float | None = None
                    for attempt in range(1, attempts_total + 1):
                        if self._stop_requested:
                            break
                        passed, value = self._run_step(step)
                        if passed or attempt == attempts_total:
                            break
                        self._emit_log(
                            "info",
                            f"{step.name}: attempt {attempt}/{attempts_total} "
                            "failed, retrying...",
                        )

                    if not passed:
                        overall_passed = False

                    payload: TestResultPayload = {
                        "value": value if value is not None else 0.0,
                        "min": step.min_val if step.min_val is not None else 0.0,
                        "max": step.max_val if step.max_val is not None else 0.0,
                        "unit": step.unit,
                        "passed": passed,
                        "is_measurement": (
                            step.has_limits or self._has_promptyesno(step)
                        ) and value is not None,
                    }
                    self.test_result.emit(step.name, dict(payload))
                    self._run_record.results.append(
                        {"test_name": step.name, "loop": loop_number, **dict(payload)}
                    )
                    if self._secure_log is not None:
                        try:
                            self._secure_log.log(
                                "test_result",
                                {
                                    "test_name": step.name,
                                    "passed": passed,
                                    "value": payload.get("value"),
                                    "min": payload.get("min"),
                                    "max": payload.get("max"),
                                    "unit": payload.get("unit"),
                                    "is_measurement": payload.get(
                                        "is_measurement", True
                                    ),
                                },
                            )
                        except Exception:
                            pass

                    self.progress_test.emit(100)
                    completed += 1
                    self.progress_total.emit(
                        min(100, int((completed / total_steps) * 100))
                    )

                    if step.is_critical and not passed:
                        self._emit_log(
                            "error",
                            f"CRITICAL ABORT: {step.name} failed; halting sequence.",
                        )
                        abort_all_loops = True
                        break

                    if self._stop_on_fail and not passed:
                        self._emit_log(
                            "info",
                            f"Stop on fail: {step.name} failed; aborting remaining tests.",
                        )
                        abort_all_loops = True
                        break

                if abort_all_loops:
                    break

        finally:
            try:
                self._hw.disconnect()
            except Exception:
                pass
            self._run_record.end_time = datetime.now()
            self._run_record.overall_passed = overall_passed
            try:
                self._db.save_run(self._run_record)
            except Exception as exc:
                self._emit_log("error", f"ERROR: failed to save run to database: {exc!s}")
            self.current_test.emit("")
            self.progress_test.emit(0)
            self._pause_event.set()
            self.finished.emit()

    def _run_step(self, step: TestStep) -> tuple[bool, float | None]:
        """Execute every command in `step`; return (passed, last_measurement)."""
        last_measurement: float | None = None
        n = max(1, len(step.commands))

        # Optional: hand the active step's expected unit/limits to drivers that
        # want it (e.g. test-specific mocks that read one channel for both volts
        # and amps). No-op for drivers without the method — the default
        # MockHardware does not implement it.
        set_ctx = getattr(self._hw, "set_active_step", None)
        if callable(set_ctx):
            try:
                set_ctx(step.unit, step.min_val, step.max_val)
            except Exception:
                pass

        for idx, cmd in enumerate(step.commands, start=1):
            if self._stop_requested:
                return False, last_measurement
            try:
                result = self._execute_command(cmd)
                if result is not None:
                    last_measurement = result
            except Exception as exc:
                self._emit_log(
                    "error",
                    f"ERROR in {step.name}: command {cmd['cmd']!r} raised: {exc!s}",
                )
                return False, last_measurement

            self.progress_test.emit(min(99, int((idx / n) * 100)))

        if step.has_limits:
            if last_measurement is None:
                self._emit_log(
                    "error",
                    f"{step.name}: validation error - Limits set but no "
                    "measurement command executed; marking FAIL.",
                )
                return False, None
            assert step.min_val is not None and step.max_val is not None
            in_spec = step.min_val <= last_measurement <= step.max_val
            return in_spec, last_measurement

        # PromptYesNo without explicit Limits: Yes (1.0) → pass, No (0.0) → fail
        if last_measurement is not None and self._has_promptyesno(step):
            return last_measurement > 0.5, last_measurement

        return True, last_measurement

    @staticmethod
    def _has_promptyesno(step: TestStep) -> bool:
        return any(str(cmd["cmd"]).lower() == "promptyesno" for cmd in step.commands)

    def _execute_command(self, cmd: dict) -> float | None:
        """Dispatch one command.

        Intercepts the runner-side commands `Delay`, `Log`, and `Prompt`
        before falling through to the hardware driver.
        """
        name = str(cmd["cmd"]).lower()
        args = cmd["args"]

        if name == "delay":
            if not args:
                raise ValueError("'Delay' requires a millisecond argument")
            self.msleep(int(float(args[0])))
            return None

        if name == "log":
            self.script_log.emit(" ".join(args))
            return None

        if name == "prompt":
            self._prompt_event.clear()
            self.prompt_request.emit(" ".join(args))
            self._prompt_event.wait()
            return None

        if name == "promptyesno":
            self._yesno_event.clear()
            self._yesno_answer = False
            self.prompt_yesno_request.emit(" ".join(args))
            self._yesno_event.wait()
            answer_val = 1.0 if self._yesno_answer else 0.0
            self._emit_log(
                "info",
                f"PromptYesNo response: {'Yes' if self._yesno_answer else 'No'} ({answer_val:g})",
            )
            return answer_val

        value = self._hw.execute_command(name, args)
        return value if name in self._hw.measurement_commands else None

    def resume(self) -> None:
        """Unblock a thread parked on a `Prompt` (called by the UI thread)."""
        self._prompt_event.set()

    def submit_yesno_answer(self, answer: bool) -> None:
        """Supply the Yes/No answer and unblock the runner (called by the UI thread)."""
        self._yesno_answer = answer
        self._yesno_event.set()

    def pause(self) -> None:
        """Request pause between steps."""
        self._pause_event.clear()

    def resume_pause(self) -> None:
        """Resume after Pause."""
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_requested = True
        self._prompt_event.set()
        self._yesno_event.set()
        self._pause_event.set()

    def report_snapshot(self) -> tuple[dict, list[dict]]:
        """Header meta and result rows for PDF/CSV (after finished)."""
        end = self._run_record.end_time or datetime.now()
        meta = {
            "overall_result": "PASS" if self._run_record.overall_passed else "FAIL",
            "tester_name": self.tester_name,
            "employee_id": self.employee_id,
            "test_program_name": self._logical_script_name,
            "uut_type": self.uut_type,
            "part_number": self._run_record.part_number,
            "serial_number": self._run_record.serial_number,
            "start_time": self._run_record.start_time.isoformat(timespec="seconds"),
            "end_time": end.isoformat(timespec="seconds"),
        }
        rows: list[dict] = []
        for r in self._run_record.results:
            rows.append(
                {
                    "test_name": r.get("test_name", ""),
                    "value": r.get("value"),
                    "min": r.get("min"),
                    "max": r.get("max"),
                    "unit": r.get("unit", ""),
                    "passed": bool(r.get("passed")),
                    "is_measurement": r.get("is_measurement", True),
                    "loop": int(r.get("loop", 1)),
                }
            )
        meta["loop_count"] = self._loop_count
        return meta, rows
