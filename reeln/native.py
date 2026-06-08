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


def state_to_json(state: object) -> str:
    """Serialize a Python GameState to JSON for reeln_native mutations."""
    import json

    from reeln.models.game import game_state_to_dict

    return json.dumps(game_state_to_dict(state))  # type: ignore[arg-type]


def json_to_state(json_str: str) -> object:
    """Deserialize JSON from reeln_native back to a Python GameState."""
    import json

    from reeln.models.game import dict_to_game_state

    return dict_to_game_state(json.loads(json_str))
