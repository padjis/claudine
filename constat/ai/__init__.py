"""The interpretation layer.

Isolated behind a provider interface (D-003). The evidence pipeline has no
dependency on anything in here: with no provider configured the whole
workflow runs, reports evidence, and states that no rules were identified
rather than implying none exist (D-039).

Everything a provider is given passes through `redaction` first, which is
where the personal-data question deferred at D-023 is settled.
"""

from .provider import (
    NO_PROVIDER_NOTE,
    NULL_PROVIDER_NAME,
    Interpretation,
    NullProvider,
    Provider,
)
from .redaction import (
    CommitContext,
    FileChange,
    ProviderPayload,
    RepositoryContext,
    redact,
    scrub_diff,
    scrub_message,
)
from .settings import PROVIDER_ENV, resolve

__all__ = [
    "NO_PROVIDER_NOTE",
    "NULL_PROVIDER_NAME",
    "PROVIDER_ENV",
    "CommitContext",
    "FileChange",
    "Interpretation",
    "NullProvider",
    "Provider",
    "ProviderPayload",
    "RepositoryContext",
    "redact",
    "resolve",
    "scrub_diff",
    "scrub_message",
]
