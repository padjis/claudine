"""Workspace schema.

Versioned from the first release (D-008). A stored governance record is
useless if the schema that produced it cannot be identified.

Two integrity rules from ARCHITECTURE.md section 5 are enforced **by the
database**, not by application code: approved versions cannot be updated or
deleted. Application-level immutability is a convention a future bug can break
silently; a trigger cannot be bypassed by forgetting to call the right helper.
"""

from __future__ import annotations

SCHEMA_VERSION = 3

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

-- What ran, against which repository, and what it contributed. Without this a
-- document becomes unattributable prose, which is the failure this product
-- exists to prevent (D-029).
CREATE TABLE operation (
    id            INTEGER PRIMARY KEY,
    document_id   INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    repository_id INTEGER REFERENCES repository(id),
    kind          TEXT    NOT NULL,
    ran_at        TEXT    NOT NULL,
    summary       TEXT    NOT NULL DEFAULT '',
    payload       TEXT
);

-- A business rule, declared by a person (D-038). Not inferred from code:
-- under D-035 a rule is a business statement, and a migration or annotation
-- is at most evidence that one exists.
CREATE TABLE rule (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    statement   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
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
}
