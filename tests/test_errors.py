"""Unit tests for src/sva2rtl/errors.py."""

from __future__ import annotations

import pytest

from sva2rtl.errors import (
    InternalError,
    SlangNotFound,
    SvaCompileError,
    SvaError,
    UnsupportedConstruct,
)
from sva2rtl.ir import SourceLoc

# ── SvaError base ─────────────────────────────────────────────────────────


def test_sva_error_with_loc() -> None:
    """SvaError __str__ includes source location when present."""
    loc = SourceLoc("foo.sv", 10, 3)
    err = SvaError(message="something broke", source_loc=loc)
    result = str(err)
    assert "foo.sv:10:3" in result
    assert "something broke" in result
    assert "error:" in result


def test_sva_error_without_loc() -> None:
    """SvaError __str__ starts with 'error:' when source_loc is None."""
    err = SvaError(message="no location")
    result = str(err)
    assert result.startswith("error:")
    assert "no location" in result


def test_sva_error_default_source_loc_is_none() -> None:
    """SvaError source_loc defaults to None."""
    err = SvaError(message="test")
    assert err.source_loc is None


# ── UnsupportedConstruct ──────────────────────────────────────────────────


def test_unsupported_construct_format() -> None:
    """UnsupportedConstruct str includes SVA-E002, source loc, and construct name."""
    loc = SourceLoc("f.sv", 3, 5)
    err = UnsupportedConstruct(message="msg", construct_name="##N", source_loc=loc)
    result = str(err)
    assert "f.sv:3:5" in result
    assert "SVA-E002" in result
    assert "##N" in result
    assert "msg" in result


def test_unsupported_construct_no_loc() -> None:
    """UnsupportedConstruct omits location prefix when source_loc is None."""
    err = UnsupportedConstruct(message="use future version", construct_name="|->")
    result = str(err)
    assert "SVA-E002" in result
    assert "|->" in result
    assert "use future version" in result
    # No location prefix — should not start with something like "None:"
    assert not result.startswith("None")


def test_unsupported_construct_empty_name() -> None:
    """UnsupportedConstruct works with an empty construct_name."""
    err = UnsupportedConstruct(message="unknown")
    result = str(err)
    assert "SVA-E002" in result


# ── SlangNotFound ─────────────────────────────────────────────────────────


def test_slang_not_found_is_sva_error() -> None:
    """SlangNotFound is a subclass of SvaError."""
    err = SlangNotFound(message="not found")
    assert isinstance(err, SvaError)


def test_slang_not_found_message() -> None:
    """SlangNotFound str contains the message."""
    err = SlangNotFound(message="slang not found on PATH")
    assert "not found" in str(err)


# ── SvaCompileError ───────────────────────────────────────────────────────


def test_sva_compile_error_is_sva_error() -> None:
    """SvaCompileError is a subclass of SvaError."""
    err = SvaCompileError(message="parse error")
    assert isinstance(err, SvaError)


def test_sva_compile_error_with_loc() -> None:
    """SvaCompileError str includes location."""
    loc = SourceLoc("bad.sv", 7, 2)
    err = SvaCompileError(message="unexpected token", source_loc=loc)
    assert "bad.sv:7:2" in str(err)


# ── InternalError ─────────────────────────────────────────────────────────


def test_internal_error_is_sva_error() -> None:
    """InternalError is a subclass of SvaError."""
    err = InternalError(message="unreachable")
    assert isinstance(err, SvaError)


def test_internal_error_includes_bug_notice() -> None:
    """InternalError str includes a request to file a bug report."""
    err = InternalError(message="null pointer")
    result = str(err)
    assert "bug" in result.lower() or "issue" in result.lower()


# ── Catchability ──────────────────────────────────────────────────────────


def test_exceptions_are_catchable() -> None:
    """try/except SvaError catches all subclass exceptions."""
    with pytest.raises(SvaError):
        raise SlangNotFound(message="missing")

    with pytest.raises(SvaError):
        raise UnsupportedConstruct(message="unsupported", construct_name="##1")

    with pytest.raises(SvaError):
        raise SvaCompileError(message="compile failed")

    with pytest.raises(SvaError):
        raise InternalError(message="internal")


def test_catch_specific_before_base() -> None:
    """Specific subclasses can be caught before the base class."""
    caught_specific = False
    try:
        raise SlangNotFound(message="not found")
    except SlangNotFound:
        caught_specific = True
    except SvaError:
        pass
    assert caught_specific


def test_all_errors_are_exceptions() -> None:
    """All error classes inherit from Exception."""
    assert issubclass(SvaError, Exception)
    assert issubclass(SlangNotFound, Exception)
    assert issubclass(SvaCompileError, Exception)
    assert issubclass(UnsupportedConstruct, Exception)
    assert issubclass(InternalError, Exception)
