#!/usr/bin/env python3
"""Run one Feishu bot connector in long-connection mode."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.feishu_bot_service import (  # noqa: E402
    build_feishu_event_handler,
    get_feishu_connector,
    get_feishu_sdk_error_message,
    is_feishu_sdk_available,
)

logger = logging.getLogger("feishu_long_connection_worker")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Feishu bot long-connection worker")
    parser.add_argument("--connector-id", required=True, help="Bot connector ID")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    connector = get_feishu_connector(args.connector_id)
    if connector is None or connector.get("enabled") is False:
        logger.error("Feishu connector %s not found or disabled", args.connector_id)
        return 2
    if str(connector.get("event_receive_mode") or "").strip().lower() != "long_connection":
        logger.error("Feishu connector %s is not configured for long_connection mode", args.connector_id)
        return 2
    if not is_feishu_sdk_available():
        logger.error(get_feishu_sdk_error_message())
        return 3

    from lark_oapi.ws import Client
    from lark_oapi.ws import client as ws_client_module

    app_id = str(connector.get("app_id") or "").strip()
    app_secret = str(connector.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        logger.error("Feishu connector %s missing app_id or app_secret", args.connector_id)
        return 2

    handler = build_feishu_event_handler(connector, loop=ws_client_module.loop)
    logger.info("Starting Feishu long-connection worker for connector %s", args.connector_id)
    Client(app_id, app_secret, event_handler=handler).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
