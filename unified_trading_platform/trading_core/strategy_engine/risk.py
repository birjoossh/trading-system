"""
Risk rule helpers — canonical implementations live in engine.py.

This module re-exports them for backward compatibility.
"""

from .engine import _is_short, _hit_target, _hit_stop, _trail_stop

# Re-export with public names for callers that prefer non-underscore API
hit_target = _hit_target
hit_stop = _hit_stop
trail_stop = _trail_stop

__all__ = ["hit_target", "hit_stop", "trail_stop", "_is_short", "_hit_target", "_hit_stop", "_trail_stop"]
