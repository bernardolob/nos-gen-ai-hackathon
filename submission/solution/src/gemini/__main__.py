"""Allow ``python -m gemini`` to run the connection check."""

from .cli import main

raise SystemExit(main())
