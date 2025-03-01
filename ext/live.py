import discord 
from discord.ext import commands, tasks
from discord.ui import Button, Modal, TextInput, View
import logging
from datetime import datetime
import asyncio
import json
from typing import Optional, Dict, Any

from ext.product_manager import ProductManager
from ext.balance_manager import BalanceManager
from ext.trx import TransactionManager
from ext.constants import CURRENCY_RATES, MAX_ITEMS_PER_MESSAGE

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load config
with open('config.json') as config_file:
    config = json.load(config_file)

LIVE_STOCK_CHANNEL_ID = int(config['id_live_stock'])
COOLDOWN_SECONDS = 3
UPDATE_INTERVAL = 55

def format_datetime() -> str:
    """Get current datetime in UTC"""
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

class BuyModal(Modal, title="Buy Product"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.trx_manager = TransactionManager(bot)
        self.balance_manager = BalanceManager(bot)
        self.product_manager = ProductManager(bot)
        self.logger = logging.getLogger("BuyModal")
        
        self.product_code = TextInput(
            label="Product Code",
            placeholder="Enter product code",
            required=True,
            min_length=1,
            max_length=10,
            custom_id="product_code"
        )
        
        self.quantity = TextInput(
            label="Quantity", 
            placeholder="Enter quantity",
            required=True,
            min_length=1,
            max_length=3,
            custom_id="quantity"
        )
        
        self.add_item(self.product_code)
        self.add_item(self.quantity)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get GrowID first
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.followup.send(
                    "❌ Please set your GrowID first!", 
                    ephemeral=True
                )
                return

            # Validate quantity
            try:
                quantity = int(self.quantity.value)
                if quantity <= 0:
                    await interaction.followup.send(
                        "❌ Quantity must be positive.", 
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid quantity.", 
                    ephemeral=True
                )
                return

            product_code = self.product_code.value.upper()
            
            # Process purchase
            success, message, items = await self.trx_manager.process_purchase(
                growid,
                product_code,
                quantity
            )

            if not success:
                await interaction.followup.send(
                    f"❌ {message}", 
                    ephemeral=True
                )
                return

            # Get updated balance
            new_balance = await self.balance_manager.get_balance(growid)
            
            # Create success embed
            embed = discord.Embed(
                title="✅ Purchase Successful",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(
                name="Transaction Details",
                value=message,
                inline=False
            )
            if new_balance:
                embed.add_field(
                    name="New Balance",
                    value=new_balance.format(),
                    inline=False
                )

            # Try to send items via DM
            if items:
                try:
                    items_text = "\n".join(items)
                    dm_embed = discord.Embed(
                        title="🎉 Your Items",
                        description=f"```\n{items_text}\n```",
                        color=discord.Color.gold()
                    )
                    await interaction.user.send(embed=dm_embed)
                except discord.Forbidden:
                    embed.add_field(
                        name="⚠️ Warning",
                        value="Could not send items via DM. Please enable DMs!",
                        inline=False
                    )

            await interaction.followup.send(
                embed=embed, 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in BuyModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred during purchase.", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred during purchase.", 
                    ephemeral=True
                )

class SetGrowIDModal(Modal, title="Set GrowID"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.balance_manager = BalanceManager(bot)
        self.logger = logging.getLogger("SetGrowIDModal")
        
        self.growid = TextInput(
            label="GrowID",
            placeholder="Enter your GrowID",
            required=True,
            min_length=3,
            max_length=20,
            custom_id="growid"
        )
        
        self.add_item(self.growid)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            growid = self.growid.value.strip()
            
            if not growid.isalnum():
                await interaction.followup.send(
                    "❌ GrowID must contain only letters and numbers.", 
                    ephemeral=True
                )
                return
            
            # Register user through BalanceManager
            success = await self.balance_manager.register_user(
                interaction.user.id,
                growid
            )
            
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
            embed.set_footer(text=f"Set by: {interaction.user}")
            
            await interaction.followup.send(
                embed=embed, 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in SetGrowIDModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while setting GrowID.", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while setting GrowID.", 
                    ephemeral=True
                )

class StockView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.balance_manager = BalanceManager(bot)
        self.product_manager = ProductManager(bot)
        self.trx_manager = TransactionManager(bot)
        self._cooldowns = {}
        self._cache = {}
        self._cache_timeout = 300
        self.logger = logging.getLogger("StockView")
        self._init_buttons()

    def _init_buttons(self):
        try:
            self.clear_items()
            
            # Define button data
            buttons = [
                ("balance", "Check Balance", "💰", discord.ButtonStyle.secondary),
                ("buy", "Buy", "🛒", discord.ButtonStyle.primary),
                ("set_growid", "Set GrowID", "📝", discord.ButtonStyle.success),
                ("check_growid", "Check GrowID", "🔍", discord.ButtonStyle.secondary),
                ("world", "World Info", "🌍", discord.ButtonStyle.secondary)
            ]
            
            # Create and add buttons
            for custom_id, label, emoji, style in buttons:
                button = Button(
                    custom_id=f"button_{custom_id}",
                    label=label,
                    emoji=emoji,
                    style=style
                )
                button.callback = getattr(self, f"button_{custom_id}_callback")
                self.add_item(button)
                
            self.logger.info("Buttons initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing buttons: {e}")
            raise

    async def _check_cooldown(self, interaction: discord.Interaction) -> bool:
        """Check if user is on cooldown"""
        try:
            user_id = interaction.user.id
            current_time = datetime.utcnow().timestamp()
            
            if user_id in self._cooldowns:
                time_diff = current_time - self._cooldowns[user_id]
                if time_diff < COOLDOWN_SECONDS:
                    await interaction.response.send_message(
                        f"⚠️ Please wait {COOLDOWN_SECONDS - int(time_diff)} seconds before using buttons again.",
                        ephemeral=True
                    )
                    return False
                    
            self._cooldowns[user_id] = current_time
            return True
        except Exception as e:
            self.logger.error(f"Error checking cooldown: {e}")
            return False

    async def button_balance_callback(self, interaction: discord.Interaction):
        """Handle balance button click"""
        if not await self._check_cooldown(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get user's GrowID first
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.followup.send(
                    "❌ Please set your GrowID first!", 
                    ephemeral=True
                )
                return

            # Get balance
            balance = await self.balance_manager.get_balance(growid)
            if not balance:
                await interaction.followup.send(
                    "❌ Balance not found!", 
                    ephemeral=True
                )
                return

            # Get recent transactions
            transactions = await self.trx_manager.get_recent_transactions(growid, limit=5)

            embed = discord.Embed(
                title="💰 Balance Information",
                description=f"GrowID: `{growid}`",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(
                name="Current Balance", 
                value=balance.format(), 
                inline=False
            )

            if transactions:
                transactions_text = "\n".join([
                    f"• {tx['type']}: {tx['details']} ({tx['created_at']})"
                    for tx in transactions
                ])
                embed.add_field(
                    name="Recent Transactions",
                    value=transactions_text,
                    inline=False
                )
            
            await interaction.followup.send(
                embed=embed, 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in balance callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while checking balance.", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while checking balance.", 
                    ephemeral=True
                )

    async def button_buy_callback(self, interaction: discord.Interaction):
        """Handle buy button click"""
        if not await self._check_cooldown(interaction):
            return

        try:
            # Check if user has GrowID
            if not await self.balance_manager.has_growid(interaction.user.id):
                await interaction.response.send_message(
                    "❌ Please set your GrowID first!", 
                    ephemeral=True
                )
                return
                
            # Show buy modal
            modal = BuyModal(self.bot)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error in buy callback: {e}")
            await interaction.response.send_message(
                "❌ An error occurred.", 
                ephemeral=True
            )

    async def button_set_growid_callback(self, interaction: discord.Interaction):
        """Handle set GrowID button click"""
        if not await self._check_cooldown(interaction):
            return
            
        try:
            modal = SetGrowIDModal(self.bot)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            self.logger.error(f"Error in set growid callback: {e}")
            await interaction.response.send_message(
                "❌ An error occurred.", 
                ephemeral=True
            )

    async def button_check_growid_callback(self, interaction: discord.Interaction):
        """Handle check GrowID button click"""
        if not await self._check_cooldown(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.followup.send(
                    "❌ You haven't set your GrowID yet!", 
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🔍 GrowID Information",
                description=f"Your registered GrowID: `{growid}`",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            await interaction.followup.send(
                embed=embed, 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in check growid callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred.", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred.", 
                    ephemeral=True
                )

    async def button_world_callback(self, interaction: discord.Interaction):
        """Handle world info button click"""
        if not await self._check_cooldown(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            world_info = await self.product_manager.get_world_info()
            if not world_info:
                await interaction.followup.send(
                    "❌ No world information available.", 
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🌍 World Information",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(
                name="World", 
                value=f"`{world_info['world']}`", 
                inline=True
            )
            if world_info.get('owner'):
                embed.add_field(
                    name="Owner", 
                    value=f"`{world_info['owner']}`", 
                    inline=True
                )
            if world_info.get('bot'):
                embed.add_field(
                    name="Bot", 
                    value=f"`{world_info['bot']}`", 
                    inline=True
                )
            
            await interaction.followup.send(
                embed=embed, 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error in world callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred.", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred.", 
                    ephemeral=True
                )

class LiveStock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_id = None
        self.update_lock = asyncio.Lock()
        self.last_update = 0
        self.product_manager = ProductManager(bot)
        self.stock_view = None
        self.logger = logging.getLogger("LiveStock")
        
        # Initialize stock view after bot is ready
        self.bot.loop.create_task(self._initialize_view())
        self.live_stock.start()
        
        print(f"Current Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Current User's Login: {self.bot.user}")

    async def _initialize_view(self):
        await self.bot.wait_until_ready()
        self.stock_view = StockView(self.bot)
        self.logger.info("StockView initialized")
        
    def cog_unload(self):
        self.live_stock.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if self.stock_view:
            self.bot.add_view(self.stock_view)
        self.logger.info("LiveStock cog is ready")

    def _create_stock_embed(self, products: list) -> discord.Embed:
        embed = discord.Embed(
            title="🏪 Store Stock Status",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        if products:
            for product in products:
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

        embed.set_footer(text=f"Last Update: {format_datetime()} UTC")
        return embed

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def live_stock(self):
        if self.update_lock.locked():
            return
            
        async with self.update_lock:
            try:
                channel = self.bot.get_channel(LIVE_STOCK_CHANNEL_ID)
                if not channel:
                    self.logger.error('Live stock channel not found')
                    return

                products = await self.product_manager.get_all_products()
                embed = self._create_stock_embed(products)

                try:
                    if self.message_id:
                        try:
                            message = await channel.fetch_message(self.message_id)
                            await message.edit(embed=embed, view=self.stock_view)
                        except discord.NotFound:
                            message = await channel.send(embed=embed, view=self.stock_view)
                            self.message_id = message.id
                    else:
                        message = await channel.send(embed=embed, view=self.stock_view)
                        self.message_id = message.id

                    self.logger.info(f"Stock updated at {format_datetime()}")
                except discord.Forbidden:
                    self.logger.error("Bot doesn't have permission to send/edit messages")
                except discord.HTTPException as e:
                    self.logger.error(f"HTTP Exception while updating stock: {e}")

            except Exception as e:
                self.logger.error(f"Error in live_stock task: {e}")
                if self.message_id:
                    try:
                        channel = self.bot.get_channel(LIVE_STOCK_CHANNEL_ID)
                        message = await channel.fetch_message(self.message_id)
                        await message.edit(content="❌ Error updating stock. Please try again later.")
                    except:
                        pass

    @live_stock.before_loop
    async def before_live_stock(self):
        await self.bot.wait_until_ready()
        self.logger.info(f"Live stock loop starting at {format_datetime()}")

    @live_stock.error
    async def live_stock_error(self, exc):
        self.logger.error(f"Error in live stock loop: {exc}")
        self.live_stock.restart()

async def setup(bot):
    try:
        await bot.add_cog(LiveStock(bot))
        logging.info("LiveStock cog loaded successfully")
    except Exception as e:
        logging.error(f"Error loading LiveStock cog: {e}")