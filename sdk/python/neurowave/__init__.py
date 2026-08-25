"""NeuroWeave Python SDK - integrate the Cognitive Runtime Platform in under five minutes."""
from .agent import CognitiveAgent
from .client import NeuroWeaveClient

__all__ = ["CognitiveAgent", "NeuroWeaveClient", "Memory"]
__version__ = "1.0.0"


def __getattr__(name: str):
    # `Memory` (embedded/local mode) depends on the `neurowave-engine`
    # package - an optional extra (`pip install "neurowave[embedded]"`), not
    # a hard dependency of this package. Importing it lazily here means
    # `from neurowave import CognitiveAgent` keeps working with just the
    # base install (REST-client-only use case) even when the extra isn't
    # present; the ImportError only surfaces if `Memory` is actually used.
    if name == "Memory":
        from .embedded import Memory
        return Memory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
