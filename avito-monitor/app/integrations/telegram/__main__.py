"""``python -m app.integrations.telegram`` entry point."""
import asyncio

from app.integrations.telegram.bot import run

if __name__ == "__main__":
    asyncio.run(run())
