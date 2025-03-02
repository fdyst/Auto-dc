import discord 
from discord.ext import commands, tasks
from discord.ui import Button, Modal, TextInput, View
import logging
from datetime import datetime
import asyncio
import json
from typing import Optional, Dict, Any

from ext.product_manager import ProductManagerService
from ext.balance_manager import BalanceManagerService
from ext.trx import TransactionManager
from ext.constants import (
    STATUS_AVAILABLE, 
    STATUS_SOLD,
    TRANSACTION_PURCHASE,
    COOLDOWN_SECONDS,
    UPDATE_INTERVAL
)

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Load config
with open('config.json') as config_file:
    config = json.load(config_file)
    LIVE_STOCK_CHANNEL_ID = int(config['id_live_stock'])

class StockView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.balance_manager = BalanceManagerService(bot)
        self.product_manager = ProductManagerService(bot)
        self.trx_manager = TransactionManager(bot)
        self._cooldowns = {}
        self.logger = logging.getLogger("StockView")
        self._init_buttons()

    def _init_buttons(self):
        buttons = [
            ("balance", "Check Balance", "💰", discord.ButtonStyle.primary),
            ("buy", "Buy Product", "🛒", discord.ButtonStyle.success),
            ("set_growid", "Set GrowID", "📝", discord.ButtonStyle.secondary),
            ("check_growid", "Check GrowID", "🔍", discord.ButtonStyle.secondary),
            ("world", "World Info", "🌍", discord.ButtonStyle.primary)
        ]

        for custom_id, label, emoji, style in buttons:
            button = Button(
                custom_id=custom_id,
                label=label,
                emoji=emoji,
                style=style
            )
            setattr(button, "callback", getattr(self, f"button_{custom_id}_callback"))
            self.add_item(button)

    async def _check_cooldown(self, interaction: discord.Interaction) -> bool:
        user_id = interaction.user.id
        now = datetime.utcnow().timestamp()
        
        if user_id in self._cooldowns:
            remaining = COOLDOWN_SECONDS - (now - self._cooldowns[user_id])
            if remaining > 0:
                try:
                    await interaction.response.send_message(
                        f"⏳ Please wait {int(remaining)} seconds.",
                        ephemeral=True
                    )
                except:
                    pass
                return False
        
        self._cooldowns[user_id] = now
        return True

    async def _safe_interaction_response(self, interaction: discord.Interaction, **kwargs):
        """Safely handle interaction responses"""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(**kwargs)
            else:
                await interaction.followup.send(**kwargs)
        except Exception as e:
            self.logger.error(f"Error sending interaction response: {e}")
    async def button_balance_callback(self, interaction: discord.Interaction):
        """Handler for balance check button"""
        if not await self._check_cooldown(interaction):
            return

        try:
            try:
                await interaction.response.defer(ephemeral=True)
                deferred = True
            except:
                deferred = False
            
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                message = "❌ Please set your GrowID first!"
                await self._safe_interaction_response(interaction, content=message, ephemeral=True)
                return

            balance = await self.balance_manager.get_balance(growid)
            if not balance:
                message = "❌ Balance not found!"
                await self._safe_interaction_response(interaction, content=message, ephemeral=True)
                return

            embed = discord.Embed(
                title="💰 Balance Information",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="GrowID", value=f"`{growid}`", inline=False)
            embed.add_field(name="Balance", value=balance.format(), inline=False)
            
            if deferred:
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await self._safe_interaction_response(interaction, embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in balance callback: {e}")
            await self._safe_interaction_response(
                interaction,
                content="❌ An error occurred.",
                ephemeral=True
            )

    async def button_buy_callback(self, interaction: discord.Interaction):
        """Handler for buy button"""
        if not await self._check_cooldown(interaction):
            return

        try:
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.response.send_message(
                    "❌ Please set your GrowID first!", 
                    ephemeral=True
                )
                return
            
            modal = BuyModal(self.bot)
            await interaction.response.send_modal(modal)

        except Exception as e:
            self.logger.error(f"Error in buy callback: {e}")
            await self._safe_interaction_response(
                interaction,
                content="❌ An error occurred.",
                ephemeral=True
            )

    async def button_set_growid_callback(self, interaction: discord.Interaction):
        """Handler for set GrowID button"""
        if not await self._check_cooldown(interaction):
            return

        try:
            modal = SetGrowIDModal(self.bot)
            await interaction.response.send_modal(modal)

        except Exception as e:
            self.logger.error(f"Error in set growid callback: {e}")
            await self._safe_interaction_response(
                interaction,
                content="❌ An error occurred.",
                ephemeral=True
            )

    async def button_check_growid_callback(self, interaction: discord.Interaction):
        """Handler for check GrowID button"""
        if not await self._check_cooldown(interaction):
            return

        try:
            try:
                await interaction.response.defer(ephemeral=True)
                deferred = True
            except:
                deferred = False
            
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                message = "❌ You haven't set your GrowID yet!"
                await self._safe_interaction_response(interaction, content=message, ephemeral=True)
                return

            embed = discord.Embed(
                title="🔍 GrowID Information",
                description=f"Your registered GrowID: `{growid}`",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            if deferred:
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await self._safe_interaction_response(interaction, embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in check growid callback: {e}")
            await self._safe_interaction_response(
                interaction,
                content="❌ An error occurred.",
                ephemeral=True
            )

    async def button_world_callback(self, interaction: discord.Interaction):
        """Handler for world info button"""
        if not await self._check_cooldown(interaction):
            return

        try:
            try:
                await interaction.response.defer(ephemeral=True)
                deferred = True
            except:
                deferred = False
            
            world_info = await self.product_manager.get_world_info()
            if not world_info:
                message = "❌ World information not available."
                await self._safe_interaction_response(interaction, content=message, ephemeral=True)
                return

            embed = discord.Embed(
                title="🌍 World Information",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="World", value=f"`{world_info['world']}`", inline=True)
            if world_info.get('owner'):
                embed.add_field(name="Owner", value=f"`{world_info['owner']}`", inline=True)
            if world_info.get('bot'):
                embed.add_field(name="Bot", value=f"`{world_info['bot']}`", inline=True)
            
            if deferred:
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await self._safe_interaction_response(interaction, embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in world callback: {e}")
            await self._safe_interaction_response(
                interaction,
                content="❌ An error occurred.",
                ephemeral=True
            )

    async def _safe_interaction_response(self, interaction: discord.Interaction, **kwargs):
        """Safely handle interaction responses"""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(**kwargs)
            else:
                await interaction.followup.send(**kwargs)
        except Exception as e:
            self.logger.error(f"Error sending interaction response: {e}")
class LiveStock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_id = None
        self.update_lock = asyncio.Lock()
        self.last_update = datetime.utcnow().timestamp()
        self.service = LiveStockService(bot)
        self.stock_view = None
        self.logger = logging.getLogger("LiveStock")
        self._task = None
        
        # Initialize view only once
        if not hasattr(bot, 'live_stock_initialized'):
            self.stock_view = StockView(bot)
            bot.add_view(self.stock_view)
            self.live_stock.start()
            self.logger.info(f"LiveStock cog initialized at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self._task and not self._task.done():
            self._task.cancel()
        if hasattr(self, 'live_stock') and self.live_stock.is_running():
            self.live_stock.cancel()
        self.logger.info(f"LiveStock cog unloaded at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def live_stock(self):
        """Update stock message"""
        if self.update_lock.locked():
            self.logger.debug("Update locked, skipping...")
            return

        async with self.update_lock:
            try:
                self.logger.debug("Updating stock message...")
                channel = self.bot.get_channel(LIVE_STOCK_CHANNEL_ID)
                if not channel:
                    self.logger.error(f'Live stock channel not found (ID: {LIVE_STOCK_CHANNEL_ID})')
                    return

                products = await self.service.product_manager.get_all_products()
                self.logger.debug(f"Found {len(products)} products")
                embed = self.service.create_stock_embed(products)

                try:
                    if self.message_id:
                        try:
                            message = await channel.fetch_message(self.message_id)
                            await message.edit(embed=embed, view=self.stock_view)
                            self.logger.debug(f"Updated existing message {self.message_id}")
                        except discord.NotFound:
                            message = await channel.send(embed=embed, view=self.stock_view)
                            self.message_id = message.id
                            self.logger.info(f"Created new message {self.message_id} (old message not found)")
                    else:
                        message = await channel.send(embed=embed, view=self.stock_view)
                        self.message_id = message.id
                        self.logger.info(f"Created initial message {self.message_id}")

                except discord.Forbidden as e:
                    self.logger.error(f"Permission error: {e}")
                except discord.HTTPException as e:
                    self.logger.error(f"HTTP error: {e}")

            except Exception as e:
                self.logger.error(f"Error in live_stock task: {e}", exc_info=True)

    @live_stock.before_loop
    async def before_live_stock(self):
        """Wait for bot to be ready before starting the loop"""
        await self.bot.wait_until_ready()
        self.logger.info("Live stock loop starting")

    @live_stock.error
    async def live_stock_error(self, exc):
        """Handle errors in the live_stock loop"""
        self.logger.error(f"Error in live stock loop: {exc}", exc_info=True)
        if self.live_stock.is_running():
            self.live_stock.restart()
            self.logger.info("Live stock loop restarted")

class LiveStockService:
    """Service class for handling live stock operations"""
    _instance = None

    def __new__(cls, bot):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, bot):
        if not hasattr(self, 'initialized'):
            self.bot = bot
            self.logger = logging.getLogger("LiveStockService")
            self.product_manager = ProductManagerService(bot)
            self.initialized = True
            self.logger.info("LiveStockService initialized")

    def create_stock_embed(self, products: list) -> discord.Embed:
        """Create stock embed"""
        embed = discord.Embed(
            title="🏪 Store Stock Status",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        if products:
            for product in sorted(products, key=lambda x: x['code']):
                value = (
                    f"💎 Code: `{product['code']}`\n"
                    f"📦 Stock: `{product['stock']}`\n"
                    f"💰 Price: `{product['price']:,} WL`\n"
                )
                if product.get('description'):
                    value += f"📝 Info: {product['description']}\n"
                
                embed.add_field(
                    name=f"🔸 {product['name']} 🔸",
                    value=value,
                    inline=False
                )
        else:
            embed.description = "No products available."

        embed.set_footer(text=f"Last Update: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        return embed

# BuyModal Implementation
class BuyModal(Modal, title="Buy Product"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.trx_manager = TransactionManager(bot)
        self.balance_manager = BalanceManagerService(bot)
        self.product_manager = ProductManagerService(bot)
        self.logger = logging.getLogger("BuyModal")
        
        self.product_code = TextInput(
            label="Product Code",
            placeholder="Enter product code (e.g., DL1)",
            required=True,
            min_length=1,
            max_length=10
        )
        self.quantity = TextInput(
            label="Quantity",
            placeholder="Enter amount (1-100)",
            required=True,
            min_length=1,
            max_length=3
        )
        
        self.add_item(self.product_code)
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Verify user has GrowID
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.followup.send("❌ Please set your GrowID first!", ephemeral=True)
                return

            # Validate quantity
            try:
                quantity = int(self.quantity.value)
                if quantity <= 0 or quantity > 100:
                    await interaction.followup.send("❌ Quantity must be between 1 and 100.", ephemeral=True)
                    return
            except ValueError:
                await interaction.followup.send("❌ Invalid quantity.", ephemeral=True)
                return

            # Process purchase
            product_code = self.product_code.value.upper()
            success, message, items = await self.trx_manager.process_purchase(
                interaction.user.id,
                product_code,
                quantity
            )

            if not success:
                await interaction.followup.send(f"❌ {message}", ephemeral=True)
                return

            # Create success embed
            embed = discord.Embed(
                title="✅ Purchase Successful",
                description=message,
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )

            # Send items via DM in chunks
            if items:
                try:
                    chunks = [items[i:i + 20] for i in range(0, len(items), 20)]
                    for i, chunk in enumerate(chunks, 1):
                        items_text = "\n".join(chunk)
                        dm_embed = discord.Embed(
                            title=f"🎉 Your Items (Part {i}/{len(chunks)})",
                            description=f"```\n{items_text}\n```",
                            color=discord.Color.gold(),
                            timestamp=datetime.utcnow()
                        )
                        await interaction.user.send(embed=dm_embed)
                except discord.Forbidden:
                    embed.add_field(
                        name="⚠️ Warning",
                        value="Could not send items via DM. Please enable DMs!",
                        inline=False
                    )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in BuyModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred during purchase.", 
                    ephemeral=True
                )

class SetGrowIDModal(Modal, title="Set GrowID"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.balance_manager = BalanceManagerService(bot)
        self.logger = logging.getLogger("SetGrowIDModal")
        
        self.growid = TextInput(
            label="GrowID",
            placeholder="Enter your GrowID",
            required=True,
            min_length=3,
            max_length=20
        )
        self.add_item(self.growid)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            growid = self.growid.value.strip().upper()
            if not growid.isalnum():
                await interaction.followup.send(
                    "❌ GrowID must contain only letters and numbers.", 
                    ephemeral=True
                )
                return
            
            success = await self.balance_manager.register_user(interaction.user.id, growid)
            if not success:
                await interaction.followup.send(
                    "❌ This GrowID is already registered to another user.", 
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="✅ GrowID Set Successfully",
                description=f"Your GrowID has been set to: `{growid}`",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.logger.info(f"Set GrowID for Discord user {interaction.user.id} to {growid}")

        except Exception as e:
            self.logger.error(f"Error in SetGrowIDModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while setting GrowID.", 
                    ephemeral=True
                )

async def setup(bot):
    """Setup the LiveStock cog"""
    if not hasattr(bot, 'live_stock_loaded'):
        await bot.add_cog(LiveStock(bot))
        bot.live_stock_loaded = True
        logging.info('LiveStock cog loaded successfully')