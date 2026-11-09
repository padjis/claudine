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
    Whether a path is a real repository, or a revision resolves, is a
    RepositoryError. Keeping them separate means "you typed it wrong" can never
    be reported as "your repository is broken".
    """


class WorkspaceError(ConstatError):
    """The workspace could not be opened, created or understood.

    Distinct from RepositoryError: this is about Constat's own stored state,
    not about the repositories it reads.
    """


class WorkspaceVersionError(WorkspaceError):
    """The workspace schema does not match this version of Constat.

    Refused rather than guessed at. Reading governance records under a schema
    you do not understand risks misinterpreting an approval, which is worse
    than failing to open the file.
    """


class RepositoryError(ConstatError):
    """The repository or a revision within it could not be read.

    Deliberately distinct from InvalidInput: the input was well-formed, but the
    world did not match it.
    """


class GitUnavailable(RepositoryError):
    """The `git` binary could not be run.

    An environment problem, not a repository problem — worth its own type so the
    user is told to install Git rather than to check their repository.
    """


class PathNotFound(RepositoryError):
    """The given path does not exist."""


class NotARepository(RepositoryError):
    """The path exists but is not a Git repository."""


class RevisionNotFound(RepositoryError):
    """A revision could not be resolved to a commit in this repository."""


class AmbiguousRevision(RepositoryError):
    """A revision matched more than one ref.

    Treated as an error rather than resolved by Git's precedence rules. Silently
    picking one would risk documenting the wrong thing while looking confident,
    which is the failure mode product rule 1 exists to prevent.
    """


class NoCommonAncestor(RepositoryError):
    """Two revisions share no common ancestor, so there is nothing to compare from.

    Happens with grafted or unrelated histories. Reported rather than silently
    treated as "everything changed".
    """


class BackwardsRange(RepositoryError):
    """The target is an ancestor of the base, so the range runs backwards.

    Under merge-base comparison (D-021) this would yield an empty diff — a
    confidently wrong "nothing changed". Almost always means base and target
    were supplied the wrong way round, so it is refused rather than reported as
    no change.
    """


class GitCommandFailed(RepositoryError):
    """A git command failed for a reason Constat does not model.

    Carries the command and stderr so the cause stays inspectable rather than
    being flattened into a generic message.
    """
