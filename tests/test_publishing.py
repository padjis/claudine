"""Tests for publishing a document (CON-57, D-058).

Publishing is the only path in Constat that writes outside its own workspace,
so these tests are mostly about what it refuses and what it leaves behind.

A real bare repository stands in for a wiki, reached over `file://`. No
network, no credential, and the assertions are against what actually landed in
the target rather than against a mock's call log — a mock would happily record
a push that git would have rejected.

Five properties:

1. **A document reaches the target, and it is the stored one.** What lands is
   what `document --show` prints; nothing is re-rendered on the way out.
2. **A credential refuses the publication, and leaves the target untouched.**
   The gate runs before anything is cloned (D-047, D-058).
3. **A target is never guessed.** No remote, an unreadable remote and an
   unknown host all refuse and ask for `--target` (D-028's posture).
4. **A publication is recorded, and only after it happened.** An operation row
   for a failed publish would claim a disclosure that never occurred.
5. **Nothing else publishes.** `gather` cannot, and acceptance does not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from constat.ai.scanning import guard_publication, scan_document
from constat.errors import (
    PublicationRefused,
    PublishFailed,
    DecisionsNotReadable,
    TargetUnknown,
)
from constat.git.adapter import discover_repository
from constat.operations import gather, publish_document
from constat.publish import GitPages
from constat.publish.targets.git_pages import _host_of, detect, wiki_url
from constat.store import Registry, Review, TicketStore, Workspace

from helpers import git
from test_acceptance import a_reading, record
from test_runs import distinct_subject


@pytest.fixture
def workspace(tmp_path: Path):
    with Workspace.create(tmp_path / "ws") as ws:
        yield ws


@pytest.fixture
def wiki(tmp_path: Path) -> str:
    """A bare repository with one commit, standing in for a wiki.

    Seeded so the ordinary case is "a documentation repository that already has
    history". The empty case publishes too — Constat makes the first commit —
    and has its own test.
    """
    bare = tmp_path / "wiki.git"
    git(tmp_path, "init", "--quiet", "--bare", str(bare))
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "--quiet", "--initial-branch=main")
    git(seed, "commit", "--quiet", "--allow-empty", "-m", "init")
    git(seed, "push", "--quiet", str(bare), "HEAD:refs/heads/main")
    return f"file://{bare}"


@pytest.fixture
def subject(workspace, tmp_path: Path):
    Registry(workspace).add(
        str(distinct_subject(tmp_path, "billing", "LIMIT = 250\n")), alias="billing"
    )
    TicketStore(workspace).add("622")
    gather(workspace, "622")
    return workspace


def page_in(wiki_url_: str, tmp_path: Path, name: str = "622.md") -> Path:
    """Clone the target and return the published page."""
    check = tmp_path / f"check-{name}"
    git(tmp_path, "clone", "--quiet", wiki_url_, str(check))
    return check / name


class TestADocumentReachesTheTarget:
    def test_the_page_is_written_and_committed(self, subject, wiki, tmp_path):
        result = publish_document(subject, "622", GitPages(wiki))

        page = page_in(wiki, tmp_path)
        assert page.exists()
        assert result.ref.revision is not None

    def test_what_lands_is_the_stored_document(self, subject, wiki, tmp_path):
        """Not a re-render. D-056 made the document a function of stored state
        so a reviewer and a reader cannot be shown different things; publishing
        a freshly rendered body would reintroduce exactly that gap."""
        stored = TicketStore(subject).document("622").body
        publish_document(subject, "622", GitPages(wiki))

        assert page_in(wiki, tmp_path).read_text() == stored

    def test_the_commit_message_names_the_ticket(self, subject, wiki, tmp_path):
        publish_document(subject, "622", GitPages(wiki))
        check = tmp_path / "msg"
        git(tmp_path, "clone", "--quiet", wiki, str(check))

        assert "622" in git(check, "log", "-1", "--pretty=%s")

    def test_republishing_overwrites_rather_than_duplicating(
        self, subject, wiki, tmp_path
    ):
        """A document is a living view of one ticket; the durable record is the
        workspace, where `document_version` is append-only (D-004)."""
        publish_document(subject, "622", GitPages(wiki))
        gather(subject, "622")  # regenerate the body
        publish_document(subject, "622", GitPages(wiki))

        check = tmp_path / "once"
        git(tmp_path, "clone", "--quiet", wiki, str(check))
        pages = sorted(p.name for p in check.glob("*.md"))
        assert pages == ["622.md"]

    def test_an_unchanged_republish_makes_no_commit(self, subject, wiki, tmp_path):
        """`git commit` fails with nothing staged, so this would otherwise be a
        spurious failure on the most ordinary action there is."""
        publish_document(subject, "622", GitPages(wiki))
        check = tmp_path / "before"
        git(tmp_path, "clone", "--quiet", wiki, str(check))
        before = git(check, "rev-list", "--count", "HEAD")

        result = publish_document(subject, "622", GitPages(wiki))

        check2 = tmp_path / "after"
        git(tmp_path, "clone", "--quiet", wiki, str(check2))
        assert git(check2, "rev-list", "--count", "HEAD") == before
        assert result.ref.revision is not None  # still reports where it is

    def test_a_reference_cannot_escape_the_page_directory(self, wiki):
        """A reference arrives from a commit message, so it is attacker-shaped
        in the same way a filename is."""
        target = GitPages(wiki)
        assert target.page_for("../../etc/passwd") == "etc-passwd.md"
        assert "/" not in target.page_for("feature/622")
        assert target.page_for("...") == "document.md"


class TestACredentialRefusesThePublication:
    def test_a_credential_in_the_document_refuses(self, subject, wiki):
        with workspace_body(subject, '\n    aws_key = "AKIAIOSFODNN7EXAMPLE"'):
            with pytest.raises(PublicationRefused):
                publish_document(subject, "622", GitPages(wiki))

    def test_the_target_is_untouched_by_a_refusal(self, subject, wiki, tmp_path):
        """The gate runs before anything is cloned, so a refusal cannot leave a
        partial page or a commit behind."""
        with workspace_body(subject, '\n    aws_key = "AKIAIOSFODNN7EXAMPLE"'):
            with pytest.raises(PublicationRefused):
                publish_document(subject, "622", GitPages(wiki))

        check = tmp_path / "untouched"
        git(tmp_path, "clone", "--quiet", wiki, str(check))
        assert sorted(p.name for p in check.glob("*.md")) == []

    def test_the_refusal_says_nothing_was_published(self, subject, wiki):
        """A user who cannot tell whether a document left the machine has to
        assume it did. For a document carrying a credential that is the
        difference between rotating a key and not."""
        with workspace_body(subject, '\n    aws_key = "AKIAIOSFODNN7EXAMPLE"'):
            with pytest.raises(PublicationRefused) as exc:
                publish_document(subject, "622", GitPages(wiki))

        assert "Nothing has been published" in str(exc.value)
        assert "cannot be recalled" in str(exc.value)

    def test_the_location_is_reported_and_the_secret_is_not(self, subject, wiki):
        with workspace_body(subject, '\n    aws_key = "AKIAIOSFODNN7EXAMPLE"'):
            with pytest.raises(PublicationRefused) as exc:
                publish_document(subject, "622", GitPages(wiki))

        assert "aws_access_key_id" in str(exc.value)
        assert "AKIAIOSFODNN7EXAMPLE" not in str(exc.value)

    def test_an_override_publishes_and_is_recorded(self, subject, wiki, tmp_path):
        with workspace_body(subject, '\n    aws_key = "AKIAIOSFODNN7EXAMPLE"'):
            result = publish_document(
                subject, "622", GitPages(wiki), accept_scan_findings=True
            )

        assert result.scan_accepted is True
        assert len(result.scan_findings) == 1
        recorded = operations_of(subject, "publish_document")[0]
        assert json.loads(recorded["payload"])["scan_accepted"] is True

    def test_the_gate_shares_the_payload_scanner(self):
        """Reuse, not re-derivation — the CON-49 lesson. Both entry points go
        through `_scan_line`, so a detector added for one covers the other."""
        findings = scan_document('token = "AKIAIOSFODNN7EXAMPLE"')
        # Both detectors fire on this line: the key's own format, and the
        # assignment heuristic. Asserting the set rather than one name, because
        # which detectors exist is `scanning`'s business and not this gate's.
        assert "aws_access_key_id" in {f.detector for f in findings}
        assert all(f.line == 1 for f in findings)

    def test_a_clean_document_returns_no_findings(self):
        assert guard_publication("# Ticket 622\n\nA transfer is refused.") == ()


class TestATargetIsNeverGuessed:
    def test_a_repository_with_no_remote_refuses(self, tmp_path):
        bare = tmp_path / "lonely"
        bare.mkdir()
        git(bare, "init", "--quiet")

        with pytest.raises(TargetUnknown) as exc:
            detect(discover_repository(str(bare)))

        assert "--target" in str(exc.value)

    def test_an_unknown_host_refuses(self, tmp_path):
        repo = tmp_path / "internal"
        repo.mkdir()
        git(repo, "init", "--quiet")
        git(repo, "remote", "add", "origin", "https://git.internal.example/t/a.git")

        with pytest.raises(TargetUnknown) as exc:
            detect(discover_repository(str(repo)))

        assert "git.internal.example" in str(exc.value)
        # And it names what it does know, so the refusal is actionable.
        assert "github.com" in str(exc.value)

    def test_a_remote_with_no_readable_host_refuses(self, tmp_path):
        """A local path is a valid remote and has no host. Publishing to a
        guess derived from it would be a push to an invented URL."""
        repo = tmp_path / "pathremote"
        repo.mkdir()
        git(repo, "init", "--quiet")
        git(repo, "remote", "add", "origin", "/srv/git/thing")

        with pytest.raises(TargetUnknown):
            detect(discover_repository(str(repo)))

    def test_a_recognised_host_derives_the_wiki(self, tmp_path):
        repo = tmp_path / "gh"
        repo.mkdir()
        git(repo, "init", "--quiet")
        git(repo, "remote", "add", "origin", "https://github.com/owner/app.git")

        target = detect(discover_repository(str(repo)))
        assert target.url == "https://github.com/owner/app.wiki.git"
        assert "derived from" in target.describe()

    def test_ssh_remotes_are_recognised(self):
        """`git@github.com:owner/app.git` is not a URL any parser handles.
        Treating it as hostless would make every SSH remote unrecognised."""
        assert _host_of("git@github.com:owner/app.git") == "github.com"
        assert _host_of("ssh://git@gitlab.com/g/p") == "gitlab.com"
        assert _host_of("https://GitHub.com/o/a") == "github.com"
        assert _host_of("/srv/git/thing") is None

    def test_the_wiki_convention_does_not_double_the_suffix(self):
        assert wiki_url("https://github.com/o/a.git").endswith("a.wiki.git")
        assert wiki_url("https://github.com/o/a").endswith("a.wiki.git")

    def test_an_explicit_target_skips_detection_entirely(self, subject, wiki):
        """`--target` has to work where detection cannot: a `file://` remote
        has no host, and the tests themselves depend on this."""
        result = publish_document(subject, "622", GitPages(wiki))
        assert result.ref.target == "git-pages"

    def test_an_unreachable_target_fails_without_claiming_success(
        self, subject, tmp_path
    ):
        missing = f"file://{tmp_path / 'does-not-exist.git'}"

        with pytest.raises(PublishFailed) as exc:
            publish_document(subject, "622", GitPages(missing))

        assert "Nothing has been published" in str(exc.value)

    def test_an_empty_repository_publishes(self, subject, tmp_path):
        """Written after a wrong assumption: this was expected to fail, and
        does not. Git clones an empty repository, commits on an unborn branch
        and pushes, so Constat makes the first commit — which is the right
        behaviour for a documentation repository nobody has written to yet."""
        bare = tmp_path / "never-written.git"
        git(tmp_path, "init", "--quiet", "--bare", str(bare))

        result = publish_document(subject, "622", GitPages(f"file://{bare}"))

        assert result.ref.revision is not None
        check = tmp_path / "from-empty"
        git(tmp_path, "clone", "--quiet", f"file://{bare}", str(check))
        assert (check / "622.md").exists()

    def test_a_missing_repository_explains_the_wiki_case(self, subject, tmp_path):
        """The failure the previous test was mistaken for. On GitHub and GitLab
        a wiki does not exist until it is opened once."""
        with pytest.raises(PublishFailed) as exc:
            publish_document(
                subject, "622", GitPages(f"file://{tmp_path / 'absent.git'}")
            )

        assert "does not exist" in str(exc.value)
        assert "opened once in the browser" in str(exc.value)


class TestThePublicationIsRecorded:
    def test_an_operation_records_where_it_went(self, subject, wiki):
        result = publish_document(subject, "622", GitPages(wiki))
        recorded = operations_of(subject, "publish_document")

        assert len(recorded) == 1
        payload = json.loads(recorded[0]["payload"])
        assert payload["target"] == "git-pages"
        assert payload["revision"] == result.ref.revision
        assert payload["characters"] > 0

    def test_it_belongs_to_a_run(self, subject, wiki):
        """D-049: an operation nobody can attribute to a run is a weaker
        record than none, because it looks complete."""
        result = publish_document(subject, "622", GitPages(wiki))
        assert operations_of(subject, "publish_document")[0]["run_id"] == result.run_id

    def test_a_refused_publication_records_nothing(self, subject, wiki):
        """The ordering that matters. An operation row for a publication that
        did not happen is a false record of disclosure."""
        with workspace_body(subject, '\n    aws_key = "AKIAIOSFODNN7EXAMPLE"'):
            with pytest.raises(PublicationRefused):
                publish_document(subject, "622", GitPages(wiki))

        assert operations_of(subject, "publish_document") == []

    def test_a_failed_write_records_nothing(self, subject, tmp_path):
        with pytest.raises(PublishFailed):
            publish_document(
                subject, "622", GitPages(f"file://{tmp_path / 'nope.git'}")
            )

        assert operations_of(subject, "publish_document") == []


class TestNothingElsePublishes:
    def test_gathering_does_not_publish(self, subject, wiki, tmp_path):
        """There is no --publish on gather, and no publication as a side
        effect: a document leaves the machine only by its own command."""
        gather(subject, "622")

        check = tmp_path / "after-gather"
        git(tmp_path, "clone", "--quiet", wiki, str(check))
        assert sorted(p.name for p in check.glob("*.md")) == []

    def test_accepting_does_not_publish(self, subject, wiki, tmp_path):
        proposal_id = record(subject, a_reading())
        Review(subject).accept(proposal_id, decided_by="emmanuel")

        check = tmp_path / "after-accept"
        git(tmp_path, "clone", "--quiet", wiki, str(check))
        assert sorted(p.name for p in check.glob("*.md")) == []

    def test_a_target_cannot_report_decisions_yet(self, wiki):
        """CON-58. Raising rather than returning none: an empty list of
        decisions reads as 'nobody has decided' (D-041)."""
        with pytest.raises(DecisionsNotReadable) as exc:
            GitPages(wiki).read_decisions("622")

        assert "CON-58" in str(exc.value)
        assert "nobody has decided" in str(exc.value)

    def test_publishing_leaves_no_temporary_clone_behind(self, subject, wiki):
        import tempfile

        before = set(Path(tempfile.gettempdir()).glob("constat-publish-*"))
        publish_document(subject, "622", GitPages(wiki))
        after = set(Path(tempfile.gettempdir()).glob("constat-publish-*"))

        assert after == before

    def test_a_failed_publish_also_cleans_up(self, subject, tmp_path):
        import tempfile

        before = set(Path(tempfile.gettempdir()).glob("constat-publish-*"))
        with pytest.raises(PublishFailed):
            publish_document(subject, "622", GitPages(f"file://{tmp_path / 'x.git'}"))
        after = set(Path(tempfile.gettempdir()).glob("constat-publish-*"))

        assert after == before


# --- helpers -----------------------------------------------------------------


class workspace_body:
    """Append text to a document body for the duration of a block.

    A context manager so a test that appends a credential cannot leak it into
    the next test through a shared fixture.
    """

    def __init__(self, workspace: Workspace, extra: str) -> None:
        self._workspace = workspace
        self._extra = extra
        self._original: str | None = None

    def __enter__(self):
        self._original = TicketStore(self._workspace).document("622").body
        with self._workspace.transaction() as ws:
            ws.execute("UPDATE document SET body = ?", (self._original + self._extra,))
        return self

    def __exit__(self, *exc):
        with self._workspace.transaction() as ws:
            ws.execute("UPDATE document SET body = ?", (self._original,))
        return False


def operations_of(workspace: Workspace, kind: str) -> list:
    return workspace.execute(
        "SELECT * FROM operation WHERE kind = ? ORDER BY id", (kind,)
    ).fetchall()
