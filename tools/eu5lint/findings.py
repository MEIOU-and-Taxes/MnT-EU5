"""Finding data, severity policy, and output formatting."""

from dataclasses import dataclass
from enum import Enum
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"
    OFF = "off"


DEFAULT_SEVERITY: dict[str, Severity] = {
    "EU5001": Severity.ERROR,
    "EU5002": Severity.ERROR,
    "EU5003": Severity.WARN,
    "EU5010": Severity.ERROR,
    "EU5020": Severity.ERROR,
    "EU5021": Severity.ERROR,
    "EU5030": Severity.ERROR,
    "EU5031": Severity.ERROR,
    "EU5032": Severity.ERROR,
    "EU5040": Severity.ERROR,
    "EU5041": Severity.ERROR,
    "EU5050": Severity.ERROR,
    "EU5051": Severity.ERROR,
    "EU5052": Severity.ERROR,
    "EU5060": Severity.ERROR,
    "EU5061": Severity.ERROR,
    "EU5062": Severity.ERROR,
    "EU5070": Severity.ERROR,
    "EU5071": Severity.ERROR,
    "EU5072": Severity.ERROR,
    "EU5073": Severity.ERROR,
    "EU5080": Severity.ERROR,
    "EU5081": Severity.WARN,
    "EU5082": Severity.ERROR,
    "EU5083": Severity.ERROR,
    "EU5084": Severity.WARN,
    "EU5085": Severity.ERROR,
    "EU5086": Severity.WARN,
    "EU5087": Severity.WARN,
    "EU5090": Severity.WARN,
    "EU5091": Severity.WARN,
    "EU5092": Severity.WARN,
    "EU5100": Severity.WARN,
    "EU5110": Severity.WARN,
    "EU5120": Severity.WARN,
    "EU5130": Severity.WARN,
    "EU5900": Severity.WARN,
    "EU5901": Severity.ERROR,
}

# Plural alias for callers that prefer the wording used in the contract.
DEFAULT_SEVERITIES = DEFAULT_SEVERITY


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    col: int
    code: str
    message: str
    severity: Severity


def is_enabled(config: "Config", code: str) -> bool:
    """Would this code produce a finding, or is it switched off?

    A check whose codes are all off should not do the work behind them, and in
    particular should not ask for the base-game index: the availability warning
    that request raises would then announce that a disabled check was skipped.
    """

    default = DEFAULT_SEVERITY.get(code)
    if default is None:
        raise ValueError(f"unknown finding code {code}")
    configured = config.severity.get(code)
    return (default if configured is None else Severity(configured)) is not Severity.OFF


def make_finding(
    config: "Config",
    path: str,
    line: int,
    col: int,
    code: str,
    message: str,
) -> Finding | None:
    """Create a finding after applying the central severity override table."""

    default = DEFAULT_SEVERITY.get(code)
    if default is None:
        raise ValueError(f"unknown finding code {code}")
    configured = config.severity.get(code)
    severity = default if configured is None else Severity(configured)
    if severity is Severity.OFF:
        return None
    return Finding(
        path=path,
        line=line,
        col=col,
        code=code,
        message=message,
        severity=severity,
    )


def format_text(finding: Finding) -> str:
    return (
        f"{finding.path}:{finding.line}:{finding.col}: "
        f"{finding.code} {finding.severity.value}: {finding.message}"
    )


def format_json(finding: Finding) -> str:
    return json.dumps(
        {
            "path": finding.path,
            "line": finding.line,
            "col": finding.col,
            "code": finding.code,
            "severity": finding.severity.value,
            "message": finding.message,
        },
        ensure_ascii=False,
    )
