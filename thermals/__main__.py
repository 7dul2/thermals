"""``python -m thermals`` entry point."""

from __future__ import annotations

import sys

from thermals.cli import main

if __name__ == "__main__":
    sys.exit(main())
