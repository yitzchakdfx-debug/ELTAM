"""Manage `.tst` test-script files: raw text I/O for the editor and a
keyword-driven parser that produces executable `TestStep` lists.
"""

from __future__ import annotations

from pathlib import Path
import re

from logic.models import ScriptDocument, TestStep
from paths import user_data_path


class ScriptParseError(ValueError):
    """Raised when a `.tst` file cannot be parsed.

    Carries `line_no` (1-based) and the offending `line` text so callers can
    surface a precise diagnostic to the user.
    """

    def __init__(self, line_no: int, line: str, msg: str) -> None:
        super().__init__(f"line {line_no}: {msg} ({line!r})")
        self.line_no = line_no
        self.line = line
        self.msg = msg


class ScriptManager:
    """Discovery, raw read/write, and parsing of `.tst` test-script files."""

    SCRIPT_SUFFIX: str = ".tst"
    _KEYWORDS: frozenset[str] = frozenset(
        {"critical", "limits", "unit", "target", "retry"}
    )
    _HEADER_PARTNUM_RE = re.compile(r"^\s*(?:#\s*)?partnum\s*:\s*(.+?)\s*$", re.IGNORECASE)

    def __init__(self, scripts_dir: Path | None = None) -> None:
        self._scripts_dir: Path = (
            scripts_dir if scripts_dir is not None else user_data_path()
        )

    @property
    def scripts_dir(self) -> Path:
        return self._scripts_dir

    def list_scripts(self) -> list[Path]:
        if not self._scripts_dir.is_dir():
            return []
        return sorted(self._scripts_dir.glob(f"*{self.SCRIPT_SUFFIX}"))

    def read_script(self, path: Path) -> str:
        path = Path(path)
        self._validate_suffix(path)
        return path.read_text(encoding="utf-8")

    def write_script(self, path: Path, content: str) -> None:
        path = Path(path)
        self._validate_suffix(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def load_script(self, path: str | Path) -> list[TestStep]:
        return self.load_document(path).steps

    def load_document(self, path: str | Path) -> ScriptDocument:
        """Parse a `.tst` file into an ordered list of `TestStep` objects.

        Lines starting with `:` open a new step. Inside a step, the keywords
        `Critical`, `Limits <min> <max>`, and `Unit <str>` (case-insensitive)
        configure the step; every other non-blank, non-comment line is taken
        as a hardware command (`<cmd> <arg1> <arg2> ...`). Lines before the
        first `:` header are treated as a file preamble and ignored.
        """
        path = Path(path)
        self._validate_suffix(path)
        text = path.read_text(encoding="utf-8")

        steps: list[TestStep] = []
        metadata: dict[str, str] = {}
        current: TestStep | None = None

        for line_no, raw in enumerate(text.splitlines(), start=1):
            if current is None:
                part_match = self._HEADER_PARTNUM_RE.match(raw)
                if part_match:
                    metadata["part_number"] = part_match.group(1).strip()
                    continue
            stripped = raw.split("#", 1)[0].strip()
            if not stripped:
                continue

            if stripped.startswith(":"):
                if current is not None:
                    steps.append(current)
                name = stripped[1:].strip()
                if not name:
                    raise ScriptParseError(line_no, raw, "test name cannot be empty")
                current = TestStep(name=name)
                continue

            tokens = stripped.split()
            head = tokens[0].lower()

            if head in self._KEYWORDS:
                if current is None:
                    raise ScriptParseError(
                        line_no,
                        raw,
                        f"keyword '{tokens[0]}' appears before any ':<test name>' header",
                    )
                self._apply_keyword(current, head, tokens, line_no, raw)
                continue

            if current is None:
                raise ScriptParseError(
                    line_no,
                    raw,
                    f"command '{tokens[0]}' appears before any ':<test name>' header",
                )

            current.commands.append({"cmd": tokens[0], "args": tokens[1:]})

        if current is not None:
            steps.append(current)

        return ScriptDocument(metadata=metadata, steps=steps)

    def _apply_keyword(
        self,
        step: TestStep,
        head: str,
        tokens: list[str],
        line_no: int,
        raw: str,
    ) -> None:
        if head == "critical":
            if len(tokens) != 1:
                raise ScriptParseError(
                    line_no, raw, "'Critical' takes no arguments"
                )
            step.is_critical = True
            return

        if head == "limits":
            if step.has_limits:
                raise ScriptParseError(
                    line_no,
                    raw,
                    "step already has Target/Tol; Limits and Tolerance are mutually exclusive",
                )
            if len(tokens) != 3:
                raise ScriptParseError(
                    line_no,
                    raw,
                    "'Limits' requires exactly two numeric arguments: <min> <max>",
                )
            try:
                min_v = float(tokens[1])
                max_v = float(tokens[2])
            except ValueError as exc:
                raise ScriptParseError(
                    line_no, raw, f"'Limits' arguments must be numeric ({exc})"
                ) from exc
            if min_v > max_v:
                raise ScriptParseError(
                    line_no, raw, f"'Limits' min ({min_v}) is greater than max ({max_v})"
                )
            step.min_val = min_v
            step.max_val = max_v
            return

        if head == "target":
            if step.has_limits:
                raise ScriptParseError(
                    line_no,
                    raw,
                    "step already has Limits; Limits and Tolerance are mutually exclusive",
                )
            if len(tokens) != 4 or tokens[2].lower() != "tol":
                raise ScriptParseError(
                    line_no,
                    raw,
                    "'Target' requires syntax: Target <value> Tol <percent>",
                )
            try:
                target = float(tokens[1])
                pct = float(tokens[3])
            except ValueError as exc:
                raise ScriptParseError(
                    line_no,
                    raw,
                    f"'Target ... Tol ...' arguments must be numeric ({exc})",
                ) from exc
            if pct < 0:
                raise ScriptParseError(
                    line_no, raw, f"'Tol' percent must be non-negative (got {pct})"
                )
            step.min_val = target * (1.0 - pct / 100.0)
            step.max_val = target * (1.0 + pct / 100.0)
            return

        if head == "retry":
            if len(tokens) != 2:
                raise ScriptParseError(
                    line_no,
                    raw,
                    "'Retry' requires exactly one integer argument: <count>",
                )
            try:
                n = int(tokens[1])
            except ValueError as exc:
                raise ScriptParseError(
                    line_no, raw, f"'Retry' argument must be an integer ({exc})"
                ) from exc
            if n < 0:
                raise ScriptParseError(
                    line_no, raw, f"'Retry' count must be non-negative (got {n})"
                )
            step.retry_count = n
            return

        if head == "unit":
            if len(tokens) < 2:
                raise ScriptParseError(
                    line_no, raw, "'Unit' requires a unit string"
                )
            step.unit = " ".join(tokens[1:])
            return

    def serialize_ordered_steps(
        self, steps: list[TestStep], *, metadata: dict[str, str] | None = None
    ) -> str:
        """Build `.tst` text from ordered executable steps for version archiving."""
        lines: list[str] = []
        if metadata:
            pn = metadata.get("part_number", "").strip()
            if pn:
                lines.append(f"# PartNum: {pn}")
                lines.append("")
        for step in steps:
            lines.append(f":{step.name}")
            if step.is_critical:
                lines.append("Critical")
            if step.retry_count > 0:
                lines.append(f"Retry {step.retry_count}")
            if step.has_limits:
                mn = step.min_val
                mx = step.max_val
                assert mn is not None and mx is not None
                lines.append(f"Limits {mn:g} {mx:g}")
            if step.unit:
                lines.append(f"Unit {step.unit}")
            for cmd in step.commands:
                name = str(cmd["cmd"])
                tail = " ".join(str(a) for a in cmd["args"])
                lines.append(f"{name} {tail}".strip())
            lines.append("")
        body = "\n".join(lines).rstrip()
        return body + "\n" if body else "\n"

    _INVALID_NAME_CHARS = frozenset(r'\/:*?"<>|')

    @staticmethod
    def validate_version_name(name: str, existing_names: list[str] | None = None) -> str:
        """Validate and return a stripped version name.

        Raises ValueError with a user-facing message on failure.
        """
        clean = name.strip()
        if not clean:
            raise ValueError("Version name cannot be empty.")
        bad = ScriptManager._INVALID_NAME_CHARS & set(clean)
        if bad:
            chars = "".join(sorted(bad))
            raise ValueError(
                f'Version name cannot contain: {chars}\n'
                f'Forbidden characters: {r"\\/:*?\"<>|"}'
            )
        if existing_names is not None and clean in existing_names:
            raise ValueError(f"Version name {clean!r} already exists.")
        return clean

    def _validate_suffix(self, path: Path) -> None:
        if path.suffix.lower() != self.SCRIPT_SUFFIX:
            raise ValueError(
                f'Expected a "{self.SCRIPT_SUFFIX}" file, got "{path.suffix}" ({path}).'
            )
