import discord
from discord.ext import commands
import os
import json
import logging
import asyncio
import aiohttp
import sqlite3
from pathlib import Path
from database import setup_database, get_connection
from datetime import datetime

# Setup logging dengan file handler
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Load config dengan validasi
def load_config():
    required_keys = {
        'token': str,
        'guild_id': (int, str),  # Bisa int atau string
        'admin_id': (int, str),
        'id_live_stock': (int, str),
        'id_log_purch': (int, str),
        'id_donation_log': (int, str)
    }
    
    try:
        with open('config.json', 'r') as config_file:
            config = json.load(config_file)

        # Validate and convert types
        for key, expected_type in required_keys.items():
            if key not in config:
                raise KeyError(f"Missing required key: {key}")
            
            # Handle multiple allowed types
            if isinstance(expected_type, tuple):
                if not isinstance(config[key], expected_type):
                    config[key] = expected_type[0](config[key])
            else:
                if not isinstance(config[key], expected_type):
                    config[key] = expected_type(config[key])

        return config

    except FileNotFoundError:
        logger.error("config.json file not found!")
        raise
    except json.JSONDecodeError:
        logger.error("config.json is not valid JSON!")
        raise
    except (KeyError, ValueError) as e:
        logger.error(f"Configuration error: {e}")
        raise

# Load config
config = load_config()
TOKEN = config['token']
GUILD_ID = int(config['guild_id'])
ADMIN_ID = int(config['admin_id'])
LIVE_STOCK_CHANNEL_ID = int(config['id_live_stock'])
LOG_PURCHASE_CHANNEL_ID = int(config['id_log_purch'])
DONATION_LOG_CHANNEL_ID = int(config['id_donation_log'])

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        self.session = None
        self.admin_id = ADMIN_ID
        self.guild_id = GUILD_ID
        self.live_stock_channel_id = LIVE_STOCK_CHANNEL_ID
        self.log_purchase_channel_id = LOG_PURCHASE_CHANNEL_ID
        self.donation_log_channel_id = DONATION_LOG_CHANNEL_ID
        self.startup_time = datetime.utcnow()

# Di dalam MyBot class
    async def setup_hook(self):
        """Initialize bot components"""
        self.session = aiohttp.ClientSession()
        
        # Load extensions with proper error handling
        extensions = [
            'cogs.admin',
            'ext.live',
            'ext.trx',
            'ext.donate',
            'ext.balance_manager',
            'ext.product_manager'
        ]
        
        loaded_extensions = set()  # Track loaded extensions
        
        for ext in extensions:
            try:
                if ext not in loaded_extensions:  # Check if not already loaded
                    await self.load_extension(ext)
                    loaded_extensions.add(ext)
                    logger.info(f'✅ Loaded extension: {ext}')
            except Exception as e:
                logger.error(f'❌ Failed to load {ext}: {e}')
                raise  # Re-raise to prevent partial initialization

    async def close(self):
        """Cleanup when bot shuts down"""
        logger.info("Bot shutting down...")
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        """Event when bot is ready"""
        logger.info(f'Bot {self.user.name} is ready!')
        logger.info(f'Bot ID: {self.user.id}')
        logger.info(f'Guild ID: {self.guild_id}')
        logger.info(f'Admin ID: {self.admin_id}')
        
        # Verify channels exist
        guild = self.get_guild(self.guild_id)
        if not guild:
            logger.error(f"Could not find guild with ID {self.guild_id}")
            return

        channels = {
            'Live Stock': self.live_stock_channel_id,
            'Purchase Log': self.log_purchase_channel_id,
            'Donation Log': self.donation_log_channel_id
        }

        for name, channel_id in channels.items():
            channel = guild.get_channel(channel_id)
            if not channel:
                logger.error(f"Could not find {name} channel with ID {channel_id}")

        # Set custom status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Growtopia Shop | !help"
            ),
            status=discord.Status.online
        )

    async def on_message(self, message):
        """Handle message events"""
        if message.author.bot:
            return

        # Log messages from specific channels
        if message.channel.id in [
            self.live_stock_channel_id,
            self.log_purchase_channel_id,
            self.donation_log_channel_id
        ]:
            logger.info(
                f'Channel {message.channel.name}: '
                f'{message.author}: {message.content}'
            )

        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.errors.CheckFailure):
            await ctx.send("❌ You don't have permission to use this command!")
        elif isinstance(error, commands.errors.CommandNotFound):
            pass  # Ignore command not found
        elif isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
        elif isinstance(error, commands.errors.BadArgument):
            await ctx.send("❌ Invalid argument provided!")
        else:
            error_msg = f'Error in command {ctx.command}: {error}'
            logger.error(error_msg)
            await ctx.send(
                "❌ An error occurred! The administrator has been notified."
            )
            
            # Notify admin if serious error
            if not isinstance(error, (commands.errors.CheckFailure, commands.errors.CommandNotFound)):
                admin = self.get_user(self.admin_id)
                if admin:
                    await admin.send(f"⚠️ Bot Error:\n```{error_msg}```")

bot = MyBot()

async def main():
    """Main function to run the bot"""
    try:
        # Initialize database
        setup_database()
        logger.info("Database initialized successfully")
        
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