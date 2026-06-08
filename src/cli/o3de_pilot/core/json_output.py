# O3DE Pilot CLI - JSON Output Helper
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Standardised JSON response format for ``--json`` output.

Every command that supports ``--json`` should use :func:`json_response`
to ensure a consistent envelope:

.. code-block:: json

    {
        "status": "ok",
        "data": { ... },
        "warnings": []
    }

On error:

.. code-block:: json

    {
        "status": "error",
        "error": "Human-readable message",
        "code": "E_BUILD_FAILED"
    }
"""

from __future__ import annotations

import json
import sys
from typing import Any


def json_response(
    *,
    data: Any = None,
    warnings: list[str] | None = None,
) -> str:
    """Build a success JSON response string.

    Parameters
    ----------
    data:
        Payload — any JSON-serialisable value.
    warnings:
        Optional list of warning strings.
    """
    envelope: dict[str, Any] = {"status": "ok"}
    if data is not None:
        envelope["data"] = data
    if warnings:
        envelope["warnings"] = warnings
    return json.dumps(envelope, indent=2, default=str)


def json_error(
    message: str,
    *,
    code: str | None = None,
) -> str:
    """Build an error JSON response string.

    Parameters
    ----------
    message:
        Human-readable error description.
    code:
        Optional machine-readable error code (e.g. ``E_BUILD_FAILED``).
    """
    envelope: dict[str, Any] = {"status": "error", "error": message}
    if code:
        envelope["code"] = code
    return json.dumps(envelope, indent=2, default=str)


def emit(text: str) -> None:
    """Write JSON text to stdout and flush."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def emit_response(*, data: Any = None, warnings: list[str] | None = None) -> None:
    """Convenience: build and emit a success response."""
    emit(json_response(data=data, warnings=warnings))


def emit_error(message: str, *, code: str | None = None) -> None:
    """Convenience: build and emit an error response."""
    emit(json_error(message, code=code))
