"""WeCom group robot notification delivery."""

from __future__ import annotations

from typing import Any

import requests

from config.settings import get_settings


class WeComNotifier:
    """Small client for WeCom group robot webhooks."""

    def __init__(self, webhook_url: str | None = None, message_format: str | None = None) -> None:
        settings = get_settings()
        self.webhook_url = webhook_url or settings.wecom_webhook_url
        self.message_format = (message_format or settings.wecom_message_format).lower()
        self.timeout = settings.request_timeout_seconds

    def send_messages(self, messages: list[str]) -> list[dict[str, Any]]:
        """Send multiple chunks to WeCom."""
        return [self.send_message(message) for message in messages]

    def send_message(self, message: str) -> dict[str, Any]:
        """Send a single text or markdown message."""
        if not self.webhook_url:
            raise ValueError("WECOM_WEBHOOK_URL is not configured.")

        payload = self._build_payload(message)
        response = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if data.get("errcode") not in (0, "0"):
            raise RuntimeError(f"WeCom webhook failed: {data}")
        return data

    def _build_payload(self, message: str) -> dict[str, Any]:
        if self.message_format == "text":
            return {"msgtype": "text", "text": {"content": message}}
        return {"msgtype": "markdown", "markdown": {"content": message}}
