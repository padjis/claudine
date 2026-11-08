"""Exception types.

Kept in one place so the CLI can distinguish failure kinds and map each to a
sensible exit code, rather than letting tracebacks reach the user.
"""

from __future__ import annotations


class ConstatError(Exception):
    """Base class for every error this package raises deliberately."""


class InvalidInput(ConstatError):
    """User-supplied input is malformed.

    Raised for the *shape* of input only — an empty option, a self-comparison.
    Whether a path is a real repository, or a revision resolves, is a different
    failure and will get its own type in Session 04. Keeping them separate means
    "you typed it wrong" can never be reported as "your repository is broken".
    """
