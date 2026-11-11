"""Matching an anchor's glob against a path.

One function, shared by the grounding check (`ai/parsing.py`) and the catalogue
matcher (`store/catalogue.py`), so that "does this anchor cover this path"
cannot have two answers. Two matchers that disagree would mean a rule proposal
accepted at submit time and then never matched to a change, or the reverse.

`fnmatch` alone is not quite enough. `**/rules.py` is the natural way to write
"this file anywhere", and a model asked to anchor to evidence writes it often —
but under `fnmatch` a leading `**/` requires a directory to be present, so it
never matches a file at the repository root. Rejecting that as ungrounded would
be a false rejection of a correct anchor, and false rejections are what teach
people to stop reading them.
"""

from __future__ import annotations

from fnmatch import fnmatch

RECURSIVE_PREFIX = "**/"


def matches_path(path: str, glob: str) -> bool:
    """Whether `glob` covers `path`.

    A leading `**/` also matches at the root: `**/rules.py` covers both
    `src/rules.py` and `rules.py`. Everything else is plain `fnmatch`, where
    `*` already crosses directory separators.
    """
    if fnmatch(path, glob):
        return True
    if glob.startswith(RECURSIVE_PREFIX):
        return fnmatch(path, glob[len(RECURSIVE_PREFIX) :])
    return False
