import discord
from discord.ext import commands
import os
import json
import logging
import asyncio
import aiohttp
import sqlite3
from database import setup_database, get_connection
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Load config
try:
    with open('config.json', 'r') as config_file:
        config = json.load(config_file)

    # Bot configuration
    TOKEN = config['token']
    GUILD_ID = config['guild_id']
    ADMIN_ID = int(config['admin_id'])
    LIVE_STOCK_CHANNEL_ID = int(config['id_live_stock'])
    LOG_PURCHASE_CHANNEL_ID = int(config['id_log_purch'])
    DONATION_LOG_CHANNEL_ID = int(config['id_donation_log'])

except FileNotFoundError:
    logger.error("config.json file not found!")
    raise
except json.JSONDecodeError:
    logger.error("config.json is not valid JSON!")
    raise
except KeyError as e:
    logger.error(f"Missing required configuration key: {e}")
    raise

# Setup intents
intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        self.session = None
        self.admin_id = ADMIN_ID  # Tambahkan ini

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        print(f"Current Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Load extensions
        extensions = [
            'cogs.admin',
            'ext.live',
            'ext.trx',
            'ext.donate',
            'ext.product_manager'
        ]
        
        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info(f'Loaded extension: {ext}')
            except Exception as e:
                logger.error(f'Failed to load {ext}: {e}')
    
    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

bot = MyBot()

@bot.event
async def on_ready():
    """Event when bot is ready"""
    logger.info(f'Bot {bot.user.name} is online!')
    logger.info(f'Guild ID: {GUILD_ID}')
    logger.info(f'Admin ID: {ADMIN_ID}')
    
    # Set custom status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Growtopia Shop"
        )
    )

@bot.event
async def on_message(message):
    """Event when a message is received"""
    if message.author == bot.user:
        return
        
    logger.info(f'Message from {message.author}: {message.content}')
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.errors.CommandNotFound):
        pass
    else:
        logger.error(f'Error in {ctx.command}: {error}')
        await ctx.send(f"❌ An error occurred: {str(error)}")

async def main():
    """Main function to run the bot"""
    try:
        # Initialize database
        setup_database()
        
        # Start bot
        async with bot:
            await bot.start(TOKEN)
    except Exception as e:
        logger.error(f'Fatal error: {e}')
        raise
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.error(f'Fatal error occurred: {e}')