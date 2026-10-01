"""Backward-compatibility shim for the legacy ion namespace, pointing to aang."""
import sys
import aang

sys.modules["ion"] = aang
__all__ = ["aang"]
