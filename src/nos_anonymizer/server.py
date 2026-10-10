"""Environment-driven Uvicorn entry point."""

import uvicorn

from .api_config import ApiSettings


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(
        "nos_anonymizer.api:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        access_log=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
