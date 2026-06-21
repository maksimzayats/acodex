from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias, cast

from rich.table import Table
from rich.text import Text

from acodex.cli.presenters.base import CliPresenter

CheckPayload: TypeAlias = dict[str, Any]
FixPayload: TypeAlias = dict[str, str]
FixRows: TypeAlias = list[tuple[str, FixPayload]]

STATUS_PASS = "pass"  # noqa: S105 - doctor check status, not a password.
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
CHECK_DETAIL_KEY = "detail"
FIX_COMMAND_KEY = "command"
FIX_DETAIL_KEY = "detail"
FIX_SUMMARY_KEY = "summary"
STATUS_LABELS = MappingProxyType({
    STATUS_PASS: "PASS",
    STATUS_WARN: "WARN",
    STATUS_FAIL: "FAIL",
})
STATUS_STYLES = MappingProxyType({
    STATUS_PASS: "bold green",
    STATUS_WARN: "bold yellow",
    STATUS_FAIL: "bold red",
})


@dataclass(kw_only=True, slots=True)
class DoctorPresenter:
    """Render `acodex doctor` output."""

    base: CliPresenter = field(default_factory=CliPresenter)

    def result(self, doctor_result: dict[str, Any]) -> None:
        """Render a doctor result payload."""
        checks = doctor_result["checks"]
        self.base.console.print(self.base.panel("acodex doctor", self._checks_table(checks)))
        suggested_fixes = DoctorFixCollector().collect(checks)
        if suggested_fixes:
            self.base.console.print(
                self.base.panel("Suggested fixes", self._fix_table(suggested_fixes)),
            )
        self.base.console.print(self._summary(checks))

    def _checks_table(self, checks: list[CheckPayload]) -> Table:
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(no_wrap=True)
        table.add_column(style="bold", no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for check_payload in checks:
            check_status = str(check_payload["status"])
            table.add_row(
                Text(self._status_label(check_status), style=self._status_style(check_status)),
                str(check_payload["name"]),
                str(check_payload[CHECK_DETAIL_KEY]),
            )
        return table

    def _fix_table(self, fixes: FixRows) -> Table:
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(no_wrap=True, style="bold cyan")
        table.add_column(ratio=1, overflow="fold")
        for fix_index, (check_name, fix_payload) in enumerate(fixes, start=1):
            table.add_row(
                Text(f"{fix_index}. {check_name}", style="bold cyan"),
                self._fix_text(fix_payload),
            )
        return table

    def _fix_text(self, fix_payload: FixPayload) -> Text:
        rendered_text = Text(fix_payload[FIX_SUMMARY_KEY], style="bold white")
        if fix_payload.get(FIX_DETAIL_KEY):
            rendered_text.append("\n")
            rendered_text.append(fix_payload[FIX_DETAIL_KEY], style="dim")
        if fix_payload.get(FIX_COMMAND_KEY):
            rendered_text.append("\n$ ", style="dim")
            rendered_text.append(fix_payload[FIX_COMMAND_KEY], style="bold cyan")
        return rendered_text

    def _summary(self, checks: list[CheckPayload]) -> Text:
        counts = DoctorStatusCounter().count(checks)
        if counts[STATUS_FAIL]:
            return Text(
                "{} found; fix failures before continuing.".format(
                    self._plural(counts[STATUS_FAIL], "failing check"),
                ),
                style="bold red",
            )
        if counts[STATUS_WARN]:
            return Text(
                "No failing checks; {} need attention.".format(
                    self._plural(counts[STATUS_WARN], "warning"),
                ),
                style="bold yellow",
            )
        return Text(
            "All {} passed.".format(self._plural(counts[STATUS_PASS], "check")),
            style="bold green",
        )

    def _status_label(self, check_status: str) -> str:
        return STATUS_LABELS.get(check_status, check_status.upper())

    def _status_style(self, check_status: str) -> str:
        return STATUS_STYLES.get(check_status, "bold white")

    def _plural(self, count: int, noun: str) -> str:
        suffix = "" if count == 1 else "s"
        return f"{count} {noun}{suffix}"


@dataclass(frozen=True, slots=True)
class DoctorStatusCounter:
    """Count doctor checks by status."""

    def count(self, checks: list[CheckPayload]) -> dict[str, int]:
        """Return status counts for doctor checks."""
        counts = {STATUS_PASS: 0, STATUS_WARN: 0, STATUS_FAIL: 0}
        for check_payload in checks:
            check_status = str(check_payload["status"])
            if check_status == STATUS_PASS:
                counts[STATUS_PASS] += 1
            elif check_status == STATUS_WARN:
                counts[STATUS_WARN] += 1
            elif check_status == STATUS_FAIL:
                counts[STATUS_FAIL] += 1
        return counts


@dataclass(frozen=True, slots=True)
class DoctorFixCollector:
    """Collect unique suggested fixes from doctor checks."""

    def collect(self, checks: list[CheckPayload]) -> FixRows:
        """Return unique suggested fixes in check order."""
        fixes: FixRows = []
        seen: set[tuple[str, str, str]] = set()
        for check_payload in checks:
            fix_payload = self._fix_payload(check_payload)
            if fix_payload is None:
                continue
            fix_key = self._fix_key(fix_payload)
            if fix_key in seen:
                continue
            seen.add(fix_key)
            fixes.append((str(check_payload.get("name", "check")), fix_payload))
        return fixes

    def _fix_payload(self, check_payload: CheckPayload) -> FixPayload | None:
        raw_fix = check_payload.get("fix")
        if not isinstance(raw_fix, dict):
            return None
        fix_payload = self._normalized_fix(cast("dict[str, Any]", raw_fix))
        if not fix_payload.get(FIX_SUMMARY_KEY) and not fix_payload.get(FIX_COMMAND_KEY):
            return None
        return {fix_key: fix_value for fix_key, fix_value in fix_payload.items() if fix_value}

    def _normalized_fix(self, raw_fix: dict[str, Any]) -> FixPayload:
        return {
            FIX_SUMMARY_KEY: str(raw_fix.get(FIX_SUMMARY_KEY, "")).strip(),
            FIX_COMMAND_KEY: str(raw_fix.get(FIX_COMMAND_KEY, "")).strip(),
            FIX_DETAIL_KEY: str(raw_fix.get(FIX_DETAIL_KEY, "")).strip(),
        }

    def _fix_key(self, fix_payload: FixPayload) -> tuple[str, str, str]:
        return (
            fix_payload.get(FIX_SUMMARY_KEY, ""),
            fix_payload.get(FIX_COMMAND_KEY, ""),
            fix_payload.get(FIX_DETAIL_KEY, ""),
        )
