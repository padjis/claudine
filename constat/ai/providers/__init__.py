"""Concrete providers.

One module per provider, each implementing the `Provider` protocol and each
importing its SDK **inside** its factory rather than at module scope. That
placement is the point: `settings.PROVIDERS` names a factory, so registering a
provider costs nothing and `import constat` pulls in no HTTP client. The
dependency arrives only when someone has actually configured the provider and
a run reaches it.

Nothing here is reached except through `settings.resolve()`.
"""

from .anthropic import PROVIDER_NAME, build

__all__ = ["PROVIDER_NAME", "build"]
