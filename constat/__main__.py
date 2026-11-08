"""Allow `python -m constat`, so the CLI can be run without installing it."""

import sys

from .cli import main

sys.exit(main())
