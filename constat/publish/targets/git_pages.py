"""Publishing to a git-backed documentation repository (CON-57, D-058).

The default target, because a team's documentation usually lives next to its
code and because it needs no credential Constat has to hold: git already knows
how to authenticate, through whatever SSH agent or credential helper the user
configured. Constat inherits the environment and stays out of it.

**What it writes.** One Markdown file per ticket — `<reference>.md` — committed
and pushed. Overwriting an existing page is the normal case: the page is a view
of a living document, and the durable record is the workspace (D-004).

**Where it writes.** A clone Constat makes itself, in a temporary directory it
removes afterwards. Never the user's working tree: a failed publish must not be
able to leave a dirty checkout or a half-applied commit in a repository someone
is working in.

**How the default is derived.** From the subject repository's remote, by host.
A recognised host maps to its wiki; anything else **refuses** and asks for
`--target`. `resolve_default_branch` set that posture for D-028 and the reason
is sharper here: a wrong guess publishes a team's business rules somewhere
nobody expected to look.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from ...errors import PublishFailed, TargetUnknown
from ...git.adapter import Repository, remote_url, run_git
from ..port import NotYetReadable, PublishedRef

NAME = "git-pages"

COMMIT_SUBJECT = "Constat: document for {reference}"

WIKI_HOSTS = ("github.com", "gitlab.com", "bitbucket.org")
"""Hosts whose wiki convention is `<repository>.wiki.git`.

A short, explicit list. The alternative — treat every unknown host as if it
followed GitHub's convention — would push to a URL derived from a guess, and
`git push` to a URL that happens to exist is not recoverable by apologising."""

_SCP_LIKE = re.compile(r"^(?P<user>[^@/]+)@(?P<host>[^:/]+):(?P<path>.+)$")


def _host_of(url: str) -> str | None:
    """The host in a git remote URL, in either syntax git accepts.

    `git@github.com:owner/repo.git` is not a URL any parser handles, and
    `urllib.parse` reports no host for it — so it is matched explicitly rather
    than silently treated as hostless, which would make every SSH remote
    unrecognised.
    """
    scp = _SCP_LIKE.match(url)
    if scp is not None:
        return scp.group("host").lower()

    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]+@)?(?P<host>[^:/]+)", url)
    return match.group("host").lower() if match is not None else None


def wiki_url(url: str) -> str:
    """The wiki repository URL for a remote, by the `.wiki.git` convention."""
    return (url[: -len(".git")] if url.endswith(".git") else url) + ".wiki.git"


def detect(repo: Repository, remote: str = "origin") -> GitPages:
    """Derive the publication target from a repository's remote, or refuse.

    Never falls back to a guess. A repository with no remote, or one on a host
    whose documentation convention Constat does not know, is a case for the
    user to answer with `--target`.
    """
    url = remote_url(repo, remote)
    if url is None:
        raise TargetUnknown(
            f"{repo.root} has no `{remote}` remote, so no publication target "
            "can be derived from it. Pass --target with the URL of the "
            "documentation repository to publish to."
        )

    host = _host_of(url)
    if host is None:
        raise TargetUnknown(
            f"could not read a host from the `{remote}` remote ({url}). "
            "Pass --target explicitly rather than having Constat guess where "
            "your documentation lives."
        )
    if host not in WIKI_HOSTS:
        known = ", ".join(WIKI_HOSTS)
        raise TargetUnknown(
            f"`{remote}` points at {host}, whose documentation convention "
            f"Constat does not know (it knows: {known}). Pass --target with "
            "the URL of the documentation repository. Refusing rather than "
            "assuming GitHub's `.wiki.git` convention: a push to a guessed "
            "URL is not undone by noticing afterwards."
        )
    return GitPages(wiki_url(url), derived_from=f"{remote} ({host})")


class GitPages(NotYetReadable):
    """A git repository used as a documentation target."""

    name = NAME

    def __init__(self, url: str, *, derived_from: str | None = None) -> None:
        self.url = url
        self.derived_from = derived_from

    def describe(self) -> str:
        if self.derived_from is None:
            return self.url
        return f"{self.url} (derived from {self.derived_from})"

    def page_for(self, reference: str) -> str:
        """The page filename for a ticket.

        Sanitised because a reference reaches here from a commit message and a
        reference like `../../etc/x` must not become a path. Everything outside
        a conservative set becomes `-`.
        """
        safe = re.sub(r"[^A-Za-z0-9._-]", "-", reference).strip("-.") or "document"
        return f"{safe}.md"

    def publish(self, reference: str, body: str) -> PublishedRef:
        """Clone, write the page, commit and push. Returns where it landed."""
        workdir = Path(tempfile.mkdtemp(prefix="constat-publish-"))
        try:
            clone = workdir / "pages"
            result = run_git(["clone", "--quiet", "--depth", "1", self.url, str(clone)])
            if result.returncode != 0:
                raise PublishFailed(
                    f"could not clone the documentation repository {self.url}: "
                    f"{result.stderr.strip() or 'git clone failed'}. Nothing "
                    "has been published. An existing-but-empty repository is "
                    "fine — Constat makes the first commit — so this means the "
                    "repository is unreachable or does not exist. On GitHub "
                    "and GitLab a wiki is not created until it is opened once "
                    "in the browser."
                )

            page = clone / self.page_for(reference)
            unchanged = page.exists() and page.read_text() == body
            page.write_text(body)

            if unchanged:
                # Nothing to commit, and `git commit` would fail. Reporting it
                # as published is correct: the page holds this document.
                head = run_git(["rev-parse", "HEAD"], cwd=clone)
                return PublishedRef(
                    target=self.name,
                    location=f"{self.url} :: {self.page_for(reference)}",
                    reference=reference,
                    revision=head.stdout.strip() or None,
                )

            run_git(["add", "--", self.page_for(reference)], cwd=clone)
            committed = run_git(
                ["commit", "--quiet", "-m", COMMIT_SUBJECT.format(reference=reference)],
                cwd=clone,
            )
            if committed.returncode != 0:
                raise PublishFailed(
                    "could not commit the document: "
                    f"{committed.stderr.strip() or 'git commit failed'}. "
                    "Nothing has been published. If git reports an unknown "
                    "author, set user.name and user.email — Constat uses your "
                    "git identity rather than one of its own."
                )

            pushed = run_git(["push", "--quiet", "origin", "HEAD"], cwd=clone)
            if pushed.returncode != 0:
                raise PublishFailed(
                    f"could not push to {self.url}: "
                    f"{pushed.stderr.strip() or 'git push failed'}. Nothing "
                    "has been published; the commit exists only in a temporary "
                    "clone and is discarded."
                )

            head = run_git(["rev-parse", "HEAD"], cwd=clone)
            return PublishedRef(
                target=self.name,
                location=f"{self.url} :: {self.page_for(reference)}",
                reference=reference,
                revision=head.stdout.strip() or None,
            )
        finally:
            # Always, including after a failure: the clone may hold the
            # document, and a document is the thing being protected.
            shutil.rmtree(workdir, ignore_errors=True)
