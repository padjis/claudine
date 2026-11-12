"""Publishing a document outside the workspace (CON-57, D-058).

The one write path in Constat. Everything else — gathering, interpreting,
accepting — reads the world and writes only its own SQLite file. This writes a
rendered document to a documentation target so the people who decide about a
rule can read it where they already work (product rule 8).

Three things hold it in place, and all three are tested:

- **It is reached only by `constat publish`.** `gather` cannot publish, and
  acceptance does not publish. A document leaves the machine when someone runs
  one command that does nothing else.
- **It goes through the credential gate** (`guard_publication`), because a
  published page is the one egress that cannot be recalled (D-047, D-058).
- **It never writes to a subject repository.** The target is documentation;
  the repositories Constat reads stay read-only, as `ARCHITECTURE.md` § 6 now
  states explicitly.
"""

from .port import NotYetReadable, PublishedRef, Target
from .targets import GitPages, detect

__all__ = ["GitPages", "NotYetReadable", "PublishedRef", "Target", "detect"]
