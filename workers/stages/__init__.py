from __future__ import annotations

# Importing handlers registers all stage decorators into STAGE_HANDLERS.
from workers.stages import handlers as _handlers  # noqa: F401


def load_stage_handlers():
    return _handlers
