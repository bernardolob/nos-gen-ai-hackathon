"""Allow ``python -m nos_anonymizer`` to run the connection check."""

from .cli import main


raise SystemExit(main())
