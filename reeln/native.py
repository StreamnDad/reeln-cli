"""Bridge to the reeln_native Rust extension.

``reeln-native`` is a required dependency. This module provides a
``get_native()`` accessor for the compiled Rust functions.

Usage::

    from reeln.native import get_native

    mod = get_native()
    result = mod.probe("/path/to/video.mkv")
"""

from __future__ import annotations

import logging
from types import ModuleType

import reeln_native as _mod  # type: ignore[import-untyped,unused-ignore]

_log = logging.getLogger(__name__)
_log.debug("reeln_native %s loaded", getattr(_mod, "__version__", "?"))


def get_native() -> ModuleType:
    """Return the ``reeln_native`` module."""
    return _mod  # type: ignore[no-any-return]
