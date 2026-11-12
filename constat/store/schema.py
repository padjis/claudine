"""Workspace schema.

Versioned from the first release (D-008). A stored governance record is
useless if the schema that produced it cannot be identified.

Two integrity rules from ARCHITECTURE.md section 5 are enforced **by the
database**, not by application code: approved versions cannot be updated or
deleted. Application-level immutability is a convention a future bug can break
silently; a trigger cannot be bypassed by forgetting to call the right helper.
"""

from __future__ import annotations

SCHEMA_VERSION = 7

SCHEMA = """
CREATE TABLE schema_meta (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version  INTEGER NOT NULL,
    constat_version TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
);

-- A registered repository (D-027). `identity` is the root commit (D-025):
-- it survives the repository being moved, renamed or re-cloned, which
-- `source` and `cache_path` do not.
CREATE TABLE repository (
    id              INTEGER PRIMARY KEY,
    alias           TEXT    NOT NULL UNIQUE,
    source          TEXT    NOT NULL,
    source_kind     TEXT    NOT NULL CHECK (source_kind IN ('local', 'remote')),
    cache_path      TEXT,
    identity        TEXT,
    default_branch  TEXT,
    added_at        TEXT    NOT NULL,
    last_fetched_at TEXT
);

-- No title column. A title is unverified free text, and the provenance
-- taxonomy has no slot for "unverified label" (D-032). A reference is what
-- Constat matches on; anything descriptive must come from evidence.
CREATE TABLE ticket (
    id          INTEGER PRIMARY KEY,
    reference   TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL
);

-- Exactly one living document per ticket (D-029). The UNIQUE constraint on
-- ticket_id is the model, not an optimisation.
CREATE TABLE document (
    id          INTEGER PRIMARY KEY,
    ticket_id   INTEGER NOT NULL UNIQUE REFERENCES ticket(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    body        TEXT    NOT NULL DEFAULT ''
);

-- An immutable snapshot, frozen at approval (D-029). Append-only: see the
-- triggers below.
CREATE TABLE document_version (
    id                  INTEGER PRIMARY KEY,
    document_id         INTEGER NOT NULL REFERENCES document(id),
    version_no          INTEGER NOT NULL,
    content             TEXT    NOT NULL,
    content_hash        TEXT    NOT NULL,
    previous_version_id INTEGER REFERENCES document_version(id),
    decision            TEXT    NOT NULL CHECK (decision IN ('approved', 'rejected')),
    decided_by          TEXT    NOT NULL,
    decided_at          TEXT    NOT NULL,
    rationale           TEXT,
    UNIQUE (document_id, version_no)
);

-- One invocation that touched a document. A gather writes one `operation` row
-- per repository, so an operation row cannot answer "which run produced this";
-- a rule proposal is a reading of the evidence one run gathered (D-046,
-- D-048), and it needs something to point at. This is that something.
CREATE TABLE run (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL,
    started_at  TEXT    NOT NULL
);

-- What ran, against which repository, and what it contributed. Without this a
-- document becomes unattributable prose, which is the failure this product
-- exists to prevent (D-029).
--
-- `run_id` is nullable only because rows written before schema 4 have no run
-- to belong to. Inventing one for them would be fabricating provenance, so
-- they keep NULL and say so.
CREATE TABLE operation (
    id            INTEGER PRIMARY KEY,
    document_id   INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    run_id        INTEGER REFERENCES run(id) ON DELETE CASCADE,
    repository_id INTEGER REFERENCES repository(id),
    kind          TEXT    NOT NULL,
    ran_at        TEXT    NOT NULL,
    summary       TEXT    NOT NULL DEFAULT '',
    payload       TEXT
);

-- A business rule. Under D-035 a rule is a business statement, and no code
-- signal produces one; under D-048 it enters the catalogue only as an accepted
-- rule proposal, and can never be removed — see the trigger below.
--
-- `name` is not UNIQUE (D-050). A name is a label that may change between
-- versions; identity is this surrogate id, which survives renames,
-- restatements and anchor drift. Anchors only *match* a rule.
CREATE TABLE rule (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    statement   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

-- A rule proposal: a dated, attributed reading of the evidence one run
-- gathered (D-046, D-048). Not a rule yet, and never edited — a later run
-- makes a new reading rather than mutating this one, so "current" is derived.
--
-- `revises_rule_id` is the reading's own claim about which rule it revises,
-- found by anchor overlap and decided by the interpretation pass (D-050). NULL
-- means it claims to be new. It is a claim, not a key: a wrong one is a
-- rejectable interpretation rather than a corrupted identity.
--
-- `model` is self-reported unless `model_attested` says otherwise (D-045,
-- D-057). Submitted from outside it is a string the caller typed, nearer
-- `assumption` than `observed_fact`; on the provider path Constat issued the
-- request and read the id off the response, and only then may it be shown
-- without the caveat. One column, because the difference is not a matter of
-- degree: either Constat established it or it was told.
CREATE TABLE rule_proposal (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    statement       TEXT    NOT NULL,
    revises_rule_id INTEGER REFERENCES rule(id),
    provider        TEXT    NOT NULL,
    model           TEXT,
    model_attested  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL
);

CREATE TABLE rule_proposal_behaviour (
    id               INTEGER PRIMARY KEY,
    rule_proposal_id INTEGER NOT NULL REFERENCES rule_proposal(id) ON DELETE CASCADE,
    description      TEXT    NOT NULL
);

CREATE TABLE rule_proposal_anchor (
    id               INTEGER PRIMARY KEY,
    rule_proposal_id INTEGER NOT NULL REFERENCES rule_proposal(id) ON DELETE CASCADE,
    repository_id    INTEGER REFERENCES repository(id),
    path_glob        TEXT    NOT NULL
);

-- A human's answer to one rule proposal. Separate from the reading so that
-- accepting or rejecting does not mutate it — the same shape `document_version`
-- uses for documents (CON-31). `rejected` means inconclusive, not wrong
-- (D-036), so a later reading of better evidence is expected.
CREATE TABLE rule_proposal_decision (
    id               INTEGER PRIMARY KEY,
    rule_proposal_id INTEGER NOT NULL REFERENCES rule_proposal(id),
    decision         TEXT    NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    decided_by       TEXT    NOT NULL,
    decided_at       TEXT    NOT NULL,
    rationale        TEXT
);

-- A frozen snapshot of a rule at the moment a human accepted a reading of it.
-- Same split as document/document_version (D-029): `rule` is the current
-- state, this is the durable history. Append-only — see the triggers below.
--
-- `from_rule_proposal_id` is what makes a rule traceable: every version points
-- at the reading a human accepted to produce it, and that reading points at
-- the run whose evidence it read.
CREATE TABLE rule_version (
    id                    INTEGER PRIMARY KEY,
    rule_id               INTEGER NOT NULL REFERENCES rule(id),
    version_no            INTEGER NOT NULL,
    name                  TEXT    NOT NULL,
    statement             TEXT    NOT NULL,
    from_rule_proposal_id INTEGER NOT NULL REFERENCES rule_proposal(id),
    previous_version_id   INTEGER REFERENCES rule_version(id),
    created_at            TEXT    NOT NULL,
    UNIQUE (rule_id, version_no)
);

CREATE TABLE rule_version_behaviour (
    id              INTEGER PRIMARY KEY,
    rule_version_id INTEGER NOT NULL REFERENCES rule_version(id) ON DELETE CASCADE,
    description     TEXT    NOT NULL
);

CREATE TABLE rule_version_anchor (
    id              INTEGER PRIMARY KEY,
    rule_version_id INTEGER NOT NULL REFERENCES rule_version(id) ON DELETE CASCADE,
    repository_id   INTEGER REFERENCES repository(id),
    path_glob       TEXT    NOT NULL
);

-- A distinct way the application handles a business case under its rule.
CREATE TABLE behaviour (
    id          INTEGER PRIMARY KEY,
    rule_id     INTEGER NOT NULL REFERENCES rule(id) ON DELETE CASCADE,
    description TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    UNIQUE (rule_id, description)
);

-- Where a rule is believed to be implemented. A ticket's evidence touching an
-- anchor makes the rule impacted. `repository_id` is nullable so a rule can
-- span repositories by path pattern alone.
CREATE TABLE anchor (
    id            INTEGER PRIMARY KEY,
    rule_id       INTEGER NOT NULL REFERENCES rule(id) ON DELETE CASCADE,
    repository_id INTEGER REFERENCES repository(id) ON DELETE CASCADE,
    path_glob     TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    UNIQUE (rule_id, repository_id, path_glob)
);

CREATE INDEX idx_behaviour_rule ON behaviour(rule_id);
CREATE INDEX idx_anchor_rule ON anchor(rule_id);
CREATE INDEX idx_document_version_document ON document_version(document_id);
CREATE INDEX idx_operation_document ON operation(document_id);
CREATE INDEX idx_operation_run ON operation(run_id);
CREATE INDEX idx_run_document ON run(document_id);
CREATE INDEX idx_rule_proposal_run ON rule_proposal(run_id);
CREATE INDEX idx_rule_proposal_revises ON rule_proposal(revises_rule_id);
CREATE INDEX idx_rule_proposal_behaviour ON rule_proposal_behaviour(rule_proposal_id);
CREATE INDEX idx_rule_proposal_anchor ON rule_proposal_anchor(rule_proposal_id);
CREATE INDEX idx_rule_proposal_decision ON rule_proposal_decision(rule_proposal_id);
CREATE INDEX idx_rule_version_rule ON rule_version(rule_id);
CREATE INDEX idx_rule_version_behaviour ON rule_version_behaviour(rule_version_id);
CREATE INDEX idx_rule_version_anchor ON rule_version_anchor(rule_version_id);

-- History is durable (product rule 5), enforced here rather than trusted to
-- callers. A later approval must create a new row; it must never rewrite or
-- remove an earlier one.
CREATE TRIGGER document_version_is_append_only_update
BEFORE UPDATE ON document_version
BEGIN
    SELECT RAISE(ABORT,
        'document_version is append-only: approved versions cannot be modified');
END;

CREATE TRIGGER document_version_is_append_only_delete
BEFORE DELETE ON document_version
BEGIN
    SELECT RAISE(ABORT,
        'document_version is append-only: approved versions cannot be deleted');
END;

-- A rule cannot be removed (D-048). Enforced here because a catalogue that can
-- be emptied by a DELETE is protected by convention only, and the convention
-- is what a future bug forgets.
CREATE TRIGGER rule_cannot_be_deleted
BEFORE DELETE ON rule
BEGIN
    SELECT RAISE(ABORT,
        'a rule cannot be removed: supersede it with a new accepted rule proposal');
END;

-- A rule proposal is a reading, fixed at the moment it was made. Editing one
-- would rewrite what a reviewer was shown; deleting one would erase that it was
-- ever offered, which is the same loss D-046 refuses for discarded readings.
CREATE TRIGGER rule_proposal_is_append_only_update
BEFORE UPDATE ON rule_proposal
BEGIN
    SELECT RAISE(ABORT, 'rule_proposal is append-only: a reading cannot be edited');
END;

CREATE TRIGGER rule_proposal_is_append_only_delete
BEFORE DELETE ON rule_proposal
BEGIN
    SELECT RAISE(ABORT, 'rule_proposal is append-only: a reading cannot be deleted');
END;

CREATE TRIGGER rule_proposal_decision_is_append_only_update
BEFORE UPDATE ON rule_proposal_decision
BEGIN
    SELECT RAISE(ABORT,
        'rule_proposal_decision is append-only: a recorded decision cannot be modified');
END;

CREATE TRIGGER rule_proposal_decision_is_append_only_delete
BEFORE DELETE ON rule_proposal_decision
BEGIN
    SELECT RAISE(ABORT,
        'rule_proposal_decision is append-only: a recorded decision cannot be deleted');
END;

-- A baselined rule version is the approved record (product rule 5). A later
-- acceptance must add a version, never rewrite or remove one.
CREATE TRIGGER rule_version_is_append_only_update
BEFORE UPDATE ON rule_version
BEGIN
    SELECT RAISE(ABORT,
        'rule_version is append-only: an accepted version cannot be modified');
END;

CREATE TRIGGER rule_version_is_append_only_delete
BEFORE DELETE ON rule_version
BEGIN
    SELECT RAISE(ABORT,
        'rule_version is append-only: an accepted version cannot be deleted');
END;
"""


# Ordered migrations from one schema version to the next. A governance tool
# that discarded stored decisions on every schema change would contradict its
# own promise (product rule 5), so a version bump carries a migration rather
# than a refusal.
# Statements are listed individually rather than as a script: sqlite3's
# executescript() implicitly commits, which would silently defeat the
# surrounding transaction and could leave a workspace half-migrated.
MIGRATIONS: dict[int, tuple[str, ...]] = {
    # 1 -> 2: drop ticket.title (D-032).
    1: ("ALTER TABLE ticket DROP COLUMN title",),
    # 2 -> 3: the rule catalogue (D-038).
    2: (
        "CREATE TABLE rule ("
        " id INTEGER PRIMARY KEY,"
        " name TEXT NOT NULL UNIQUE,"
        " statement TEXT NOT NULL,"
        " created_at TEXT NOT NULL)",
        "CREATE TABLE behaviour ("
        " id INTEGER PRIMARY KEY,"
        " rule_id INTEGER NOT NULL REFERENCES rule(id) ON DELETE CASCADE,"
        " description TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " UNIQUE (rule_id, description))",
        "CREATE TABLE anchor ("
        " id INTEGER PRIMARY KEY,"
        " rule_id INTEGER NOT NULL REFERENCES rule(id) ON DELETE CASCADE,"
        " repository_id INTEGER REFERENCES repository(id) ON DELETE CASCADE,"
        " path_glob TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " UNIQUE (rule_id, repository_id, path_glob))",
        "CREATE INDEX idx_behaviour_rule ON behaviour(rule_id)",
        "CREATE INDEX idx_anchor_rule ON anchor(rule_id)",
    ),
    # 3 -> 4: a run has an identity, and operations belong to one (D-046).
    # Existing operation rows keep run_id NULL: they were written before runs
    # existed, and back-filling a run for them would fabricate provenance.
    3: (
        "CREATE TABLE run ("
        " id INTEGER PRIMARY KEY,"
        " document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,"
        " kind TEXT NOT NULL,"
        " started_at TEXT NOT NULL)",
        "ALTER TABLE operation ADD COLUMN run_id INTEGER REFERENCES run(id)",
        "CREATE INDEX idx_operation_run ON operation(run_id)",
        "CREATE INDEX idx_run_document ON run(document_id)",
    ),
    # 4 -> 5: rule proposals (D-046, D-048), and rule.name loses UNIQUE
    # (D-050).
    #
    # Dropping a constraint needs a table rebuild, and `rule` is the parent of
    # `behaviour` and `anchor` with ON DELETE CASCADE — so dropping it alone
    # would cascade the catalogue away. All three are rebuilt instead, children
    # first on the way out. Renaming `rule_new` to `rule` rewrites the new
    # children's foreign keys to match, which is why the renames come last.
    4: (
        "CREATE TABLE rule_new ("
        " id INTEGER PRIMARY KEY,"
        " name TEXT NOT NULL,"
        " statement TEXT NOT NULL,"
        " created_at TEXT NOT NULL)",
        "INSERT INTO rule_new (id, name, statement, created_at)"
        " SELECT id, name, statement, created_at FROM rule",
        "CREATE TABLE behaviour_new ("
        " id INTEGER PRIMARY KEY,"
        " rule_id INTEGER NOT NULL REFERENCES rule_new(id) ON DELETE CASCADE,"
        " description TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " UNIQUE (rule_id, description))",
        "INSERT INTO behaviour_new (id, rule_id, description, created_at)"
        " SELECT id, rule_id, description, created_at FROM behaviour",
        "CREATE TABLE anchor_new ("
        " id INTEGER PRIMARY KEY,"
        " rule_id INTEGER NOT NULL REFERENCES rule_new(id) ON DELETE CASCADE,"
        " repository_id INTEGER REFERENCES repository(id) ON DELETE CASCADE,"
        " path_glob TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " UNIQUE (rule_id, repository_id, path_glob))",
        "INSERT INTO anchor_new (id, rule_id, repository_id, path_glob, created_at)"
        " SELECT id, rule_id, repository_id, path_glob, created_at FROM anchor",
        "DROP TABLE anchor",
        "DROP TABLE behaviour",
        "DROP TABLE rule",
        "ALTER TABLE rule_new RENAME TO rule",
        "ALTER TABLE behaviour_new RENAME TO behaviour",
        "ALTER TABLE anchor_new RENAME TO anchor",
        "CREATE INDEX idx_behaviour_rule ON behaviour(rule_id)",
        "CREATE INDEX idx_anchor_rule ON anchor(rule_id)",
        "CREATE TRIGGER rule_cannot_be_deleted"
        " BEFORE DELETE ON rule BEGIN"
        " SELECT RAISE(ABORT,"
        " 'a rule cannot be removed: supersede it with a new accepted rule proposal');"
        " END",
        "CREATE TABLE rule_proposal ("
        " id INTEGER PRIMARY KEY,"
        " run_id INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,"
        " name TEXT NOT NULL,"
        " statement TEXT NOT NULL,"
        " revises_rule_id INTEGER REFERENCES rule(id),"
        " provider TEXT NOT NULL,"
        " model TEXT,"
        " created_at TEXT NOT NULL)",
        "CREATE TABLE rule_proposal_behaviour ("
        " id INTEGER PRIMARY KEY,"
        " rule_proposal_id INTEGER NOT NULL"
        " REFERENCES rule_proposal(id) ON DELETE CASCADE,"
        " description TEXT NOT NULL)",
        "CREATE TABLE rule_proposal_anchor ("
        " id INTEGER PRIMARY KEY,"
        " rule_proposal_id INTEGER NOT NULL"
        " REFERENCES rule_proposal(id) ON DELETE CASCADE,"
        " repository_id INTEGER REFERENCES repository(id),"
        " path_glob TEXT NOT NULL)",
        "CREATE TABLE rule_proposal_decision ("
        " id INTEGER PRIMARY KEY,"
        " rule_proposal_id INTEGER NOT NULL REFERENCES rule_proposal(id),"
        " decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),"
        " decided_by TEXT NOT NULL,"
        " decided_at TEXT NOT NULL,"
        " rationale TEXT)",
        "CREATE INDEX idx_rule_proposal_run ON rule_proposal(run_id)",
        "CREATE INDEX idx_rule_proposal_revises ON rule_proposal(revises_rule_id)",
        "CREATE INDEX idx_rule_proposal_behaviour"
        " ON rule_proposal_behaviour(rule_proposal_id)",
        "CREATE INDEX idx_rule_proposal_anchor"
        " ON rule_proposal_anchor(rule_proposal_id)",
        "CREATE INDEX idx_rule_proposal_decision"
        " ON rule_proposal_decision(rule_proposal_id)",
        "CREATE TRIGGER rule_proposal_is_append_only_update"
        " BEFORE UPDATE ON rule_proposal BEGIN"
        " SELECT RAISE(ABORT,"
        " 'rule_proposal is append-only: a reading cannot be edited'); END",
        "CREATE TRIGGER rule_proposal_is_append_only_delete"
        " BEFORE DELETE ON rule_proposal BEGIN"
        " SELECT RAISE(ABORT,"
        " 'rule_proposal is append-only: a reading cannot be deleted'); END",
        "CREATE TRIGGER rule_proposal_decision_is_append_only_update"
        " BEFORE UPDATE ON rule_proposal_decision BEGIN"
        " SELECT RAISE(ABORT,"
        " 'rule_proposal_decision is append-only:"
        " a recorded decision cannot be modified'); END",
        "CREATE TRIGGER rule_proposal_decision_is_append_only_delete"
        " BEFORE DELETE ON rule_proposal_decision BEGIN"
        " SELECT RAISE(ABORT,"
        " 'rule_proposal_decision is append-only:"
        " a recorded decision cannot be deleted'); END",
    ),
    # 5 -> 6: accepted rule versions (D-053). Rules that predate acceptance
    # keep no version: they were never accepted, and inventing a version for
    # them would fabricate an approval.
    5: (
        "CREATE TABLE rule_version ("
        " id INTEGER PRIMARY KEY,"
        " rule_id INTEGER NOT NULL REFERENCES rule(id),"
        " version_no INTEGER NOT NULL,"
        " name TEXT NOT NULL,"
        " statement TEXT NOT NULL,"
        " from_rule_proposal_id INTEGER NOT NULL REFERENCES rule_proposal(id),"
        " previous_version_id INTEGER REFERENCES rule_version(id),"
        " created_at TEXT NOT NULL,"
        " UNIQUE (rule_id, version_no))",
        "CREATE TABLE rule_version_behaviour ("
        " id INTEGER PRIMARY KEY,"
        " rule_version_id INTEGER NOT NULL"
        " REFERENCES rule_version(id) ON DELETE CASCADE,"
        " description TEXT NOT NULL)",
        "CREATE TABLE rule_version_anchor ("
        " id INTEGER PRIMARY KEY,"
        " rule_version_id INTEGER NOT NULL"
        " REFERENCES rule_version(id) ON DELETE CASCADE,"
        " repository_id INTEGER REFERENCES repository(id),"
        " path_glob TEXT NOT NULL)",
        "CREATE INDEX idx_rule_version_rule ON rule_version(rule_id)",
        "CREATE INDEX idx_rule_version_behaviour"
        " ON rule_version_behaviour(rule_version_id)",
        "CREATE INDEX idx_rule_version_anchor"
        " ON rule_version_anchor(rule_version_id)",
        "CREATE TRIGGER rule_version_is_append_only_update"
        " BEFORE UPDATE ON rule_version BEGIN"
        " SELECT RAISE(ABORT,"
        " 'rule_version is append-only:"
        " an accepted version cannot be modified'); END",
        "CREATE TRIGGER rule_version_is_append_only_delete"
        " BEFORE DELETE ON rule_version BEGIN"
        " SELECT RAISE(ABORT,"
        " 'rule_version is append-only:"
        " an accepted version cannot be deleted'); END",
    ),
    # 6 -> 7: whether Constat established the model id itself (D-057).
    #
    # Existing rows keep the default of 0. Not backfilled, and not backfillable:
    # every reading recorded before this column existed arrived from outside,
    # and nothing now can establish what read evidence months ago. The same
    # honest gap as `operation.run_id` at D-049 — a NULL-equivalent that says
    # "unknown" rather than a value that says "no" by assertion.
    6: (
        "ALTER TABLE rule_proposal"
        " ADD COLUMN model_attested INTEGER NOT NULL DEFAULT 0",
    ),
}
