from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv

from trading_bot.bot import IntradayTradingBot
from trading_bot.config import BotRuntimeConfig, Credentials, IST


def main() -> None:
    load_dotenv()
    creds = Credentials(
        api_key=os.environ["KITE_API_KEY"],
        access_token=os.environ["KITE_ACCESS_TOKEN"],
        api_secret=os.environ["KITE_API_SECRET"],
    )

    capital = float(os.environ.get("TRADING_CAPITAL", "1000000"))
    symbols = [s.strip() for s in os.environ.get("NIFTY50_SYMBOLS", "").split(",") if s.strip()]
    runtime = BotRuntimeConfig(capital=capital, symbols=symbols)

    bot = IntradayTradingBot(creds=creds, runtime=runtime)
    bot.prepare_day(datetime.now(IST))
    bot.run()


if __name__ == "__main__":
    main()
