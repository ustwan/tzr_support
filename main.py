"""
Main entry point for Feedback Bot.
Runs both Telegram bot and WebSocket client concurrently.
"""

import asyncio
import logging
import os
from telegram_bot import TelegramFeedbackBot
from ws_client import FeedbackBotWSClient

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """
    Main function that runs both:
    1. Telegram bot (handles /feedback in DM, status buttons)
    2. WebSocket client (receives feedback from site)
    """
    logger.info("🚀 Starting TZR Feedback Bot...")
    
    # Check required env vars
    required_vars = ['TELEGRAM_BOT_TOKEN', 'SITE_WS_URL', 'HMAC_SECRET']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ Missing environment variables: {', '.join(missing)}")
        return
    
    # Initialize Telegram bot
    telegram_bot = TelegramFeedbackBot()
    
    # Initialize WebSocket client
    ws_client = FeedbackBotWSClient(telegram_bot)
    
    # Run both concurrently
    try:
        await asyncio.gather(
            telegram_bot.start(),
            ws_client.start()
        )
    except KeyboardInterrupt:
        logger.info("🛑 Stopping bot...")
    except Exception as e:
        logger.exception(f"❌ Fatal error: {e}")
    finally:
        await ws_client.stop()
        await telegram_bot.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("✅ Bot stopped by user")

