"""Error class hierarchy for sva2rtl.

Exit code mapping:
    0 — Success
    1 — SvaCompileError / InternalError  (SV parse error or internal bug)
    2 — UnsupportedConstruct             (SVA operator not yet implemented)
    3 — SlangNotFound                    (slang binary absent from PATH)

All errors carry an optional ``source_loc`` so that diagnostics can point to
the original SVA file/line/column rather than generated RTL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sva2rtl.ir import SourceLoc


@dataclass
class SvaError(Exception):
    """Base class for all sva2rtl diagnostic errors.

    Attributes:
        message:    Human-readable description of the error.
        source_loc: Optional source location for precise diagnostics.
    """

    message: str
    source_loc: SourceLoc | None = field(default=None)

    def __str__(self) -> str:
        if self.source_loc:
            return f"{self.source_loc}: error: {self.message}"
        return f"error: {self.message}"


@dataclass
class SlangNotFound(SvaError):
    """slang binary was not found on PATH or at the user-specified path.

    Exit code: 3.  The CLI prints an actionable install message extracted from
    the exception string.
    """


@dataclass
class SvaCompileError(SvaError):
    """SV/SVA parse error reported by slang (non-zero return code).

    Exit code: 1.
    """


@dataclass
class UnsupportedConstruct(SvaError):
    """SVA construct that is not yet implemented in this version (exit code 2).

    Attributes:
        construct_name: Short identifier for the unsupported construct,
                        e.g. ``"##N"``, ``"|->"`, ``"$rose()"`.
    """

    construct_name: str = ""

    def __str__(self) -> str:
        loc_prefix = f"{self.source_loc}: " if self.source_loc else ""
        return (
            f"{loc_prefix}error SVA-E002: unsupported construct "
            f"'{self.construct_name}': {self.message}"
        )


@dataclass
class InternalError(SvaError):
    """Internal compiler error — indicates a bug in sva2rtl itself.

    Exit code: 1.  Always includes a request to file a bug report.
    """

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base}\n  (this is a bug in sva2rtl — please file an issue)"


@dataclass
class PropertyNotFound(SvaError):
    """Property name specified via --property not found in the AST (exit code 2).

    Attributes:
        property_name: The name the user specified with --property.
        available:     List of property/assertion labels found in the AST.
    """

    property_name: str = ""
    available: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        avail_str = ", ".join(self.available) if self.available else "<none>"
        return (
            f"error SVA-E005: property '{self.property_name}' not found. "
            f"Available: [{avail_str}]"
        )
