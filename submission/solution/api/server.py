"""Environment-driven Uvicorn entry point.

Run from ``submission/solution`` with ``PYTHONPATH=src``::

    python -m api.server
"""

import uvicorn

from .settings import ApiSettings


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(
        "api.app:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        access_log=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
