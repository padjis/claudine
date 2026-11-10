"""Resolving which provider to use, from the environment only.

Two rules shape this module, and both are prohibitions rather than features.

**Credentials come from the environment and are never stored.** Not in the
workspace, not in a config file, not in a document. The workspace may record
*which* provider and model produced a proposal — that is provenance, and a
reviewer needs it — but never the key that reached them.

**A misconfiguration fails loudly.** The tempting behaviour is to fall back to
the null provider when something is missing, because then nothing ever breaks.
What it produces is a document saying "no rules were identified" for a user
who believed they had configured a provider: a confidently wrong empty result,
which is the failure mode the product exists to prevent. So an unknown
provider name and a missing credential are both errors.

The registry is empty until CON-42 implements a real provider. `resolve`
accepts an injected registry so the configuration path is testable without a
network, a key or a cost.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from ..errors import ProviderNotConfigured, UnknownProvider
from .provider import NULL_PROVIDER_NAME, NullProvider, Provider

PROVIDER_ENV = "CONSTAT_AI_PROVIDER"
"""Names the provider. Unset, empty or "none" means the null provider."""

ProviderFactory = Callable[[Mapping[str, str]], Provider]

CREDENTIAL_ENV: dict[str, str] = {}
"""Provider name → the environment variable holding its credential.
Populated alongside each real provider in CON-42."""

PROVIDERS: dict[str, ProviderFactory] = {}
"""Deliberately empty. No provider is implemented yet (CON-42), and an empty
registry is the honest way to say so — unlike an entry that exists but fails."""


def resolve(
    env: Mapping[str, str] | None = None,
    providers: Mapping[str, ProviderFactory] | None = None,
) -> Provider:
    """Resolve the configured provider, or the null provider if there is none.

    Raises `UnknownProvider` if a name is given that is not implemented, and
    `ProviderNotConfigured` if an implemented provider's credential is absent.
    Neither is downgraded to the null provider.
    """
    environ = os.environ if env is None else env
    registry = PROVIDERS if providers is None else providers

    name = (environ.get(PROVIDER_ENV) or "").strip()
    if not name or name.lower() == NULL_PROVIDER_NAME:
        return NullProvider()

    if name not in registry:
        available = ", ".join(sorted(registry)) if registry else "none"
        raise UnknownProvider(
            f"{PROVIDER_ENV}={name!r} names a provider this version of Constat "
            f"does not implement (available: {available}). Refusing rather than "
            "reporting that no rules were identified, which would be a "
            "configuration fault disguised as a finding."
        )

    credential = CREDENTIAL_ENV.get(name)
    if credential is not None and not (environ.get(credential) or "").strip():
        raise ProviderNotConfigured(
            f"provider {name!r} needs {credential} in the environment. It is "
            "read from the environment only and is never written to the "
            "workspace or to any file in this repository."
        )

    return registry[name](environ)
