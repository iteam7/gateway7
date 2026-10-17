"""Run with ``python -m gateway7 --config config/demo.yaml``."""

import argparse
import asyncio
import logging
import sys

import uvicorn

from gateway7.app import create_app
from gateway7.errors import StartupError


async def _serve(config_path: str | None, host: str, port: int) -> None:
    app = create_app(config_path)
    # Own lifespan here so startup failures are reported without Uvicorn's
    # traceback logging. Access logs are disabled because URLs can contain input.
    config = uvicorn.Config(app, host=host, port=port, lifespan="off", access_log=False)
    server = uvicorn.Server(config)
    async with app.router.lifespan_context(app):
        await server.serve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Gateway7 plugin gateway")
    parser.add_argument("--config", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    gateway_logger = logging.getLogger("gateway7")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    gateway_logger.handlers = [handler]
    gateway_logger.setLevel(logging.INFO)
    gateway_logger.propagate = False
    try:
        asyncio.run(_serve(args.config, args.host, args.port))
    except StartupError as error:
        print(f"Gateway startup failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("Gateway failed to start or serve requests", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
