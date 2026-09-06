"""ARTCB as a real user for auto-development.

Operator key ≠ human session ≠ agent. Agents act only under a human session.
"""

from artcb.autodev.user import AutodevUser, DEFAULT_WALLET, DEFAULT_AGENT_ID

__all__ = ["AutodevUser", "DEFAULT_WALLET", "DEFAULT_AGENT_ID"]
