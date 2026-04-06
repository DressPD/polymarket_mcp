from __future__ import annotations

from polymarket_mcp.bot import PolymarketBot
from polymarket_mcp.config import load_settings


def main() -> None:
    settings = load_settings()
    bot = PolymarketBot(settings)
    try:
        bot.run_forever()
    finally:
        bot.close()


if __name__ == "__main__":
    main()
