"""Built-in model adapters."""

from .openai_compatible import OpenAICompatibleModel
from .replay import ReplayModel

__all__ = ["OpenAICompatibleModel", "ReplayModel"]
