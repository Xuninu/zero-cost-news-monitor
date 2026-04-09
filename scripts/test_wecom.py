"""Send a simple test message to the configured WeCom webhook."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from notify.wecom import WeComNotifier


def main() -> None:
    """CLI entry point for a lightweight WeCom connectivity check."""
    parser = argparse.ArgumentParser(description="Send a test message to the WeCom webhook.")
    parser.add_argument(
        "--message",
        default="Zero-cost news monitor test message.",
        help="Optional custom message body.",
    )
    args = parser.parse_args()

    notifier = WeComNotifier()
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = f"{args.message}\nTime: {timestamp}"
    response = notifier.send_message(content)
    print(response)


if __name__ == "__main__":
    main()
