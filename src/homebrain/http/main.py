"""Process entry point: `homebrain` (or `make run`)."""

from __future__ import annotations

import uvicorn

from homebrain.config import load_settings
from homebrain.http.app import create_app


def run() -> None:
    settings = load_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        # On AWS the task's security group admits only the ALB, so any peer is the ALB
        # and its X-Forwarded-* headers can be trusted. Locally there is no proxy.
        proxy_headers=not settings.is_local,
        forwarded_allow_ips="*" if not settings.is_local else None,
    )


if __name__ == "__main__":
    run()
