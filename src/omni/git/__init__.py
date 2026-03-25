"""
Git integration for Omni-LLM.

Provides git operations with AI attribution and safety features.
Based on patterns from Aider's repo.py.
"""

from .repository import GitRepository

__all__ = ["GitRepository"]