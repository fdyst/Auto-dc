import logging
import asyncio
import time
from typing import Dict, Optional
from datetime import datetime

import discord
from discord.ext import commands, tasks
from discord import ui
from discord.ui import Button, View

from .constants import COOLDOWN_SECONDS, UPDATE_INTERVAL, CACHE_TIMEOUT
from .balance_manager import BalanceManagerService
from .product_manager import ProductManagerService
from .trx import TransactionManager

class BuyModal(ui.Modal, title="Buy Product"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger("BuyModal")
        self.balance_manager = BalanceManagerService(bot)
        self.product_manager = ProductManagerService(bot)
        self.trx_manager = TransactionManager(bot)

    code = ui.TextInput(
        label="Product Code",
        placeholder="Enter product code...",
        min_length=1,
        max_length=10,
        required=True
    )

    quantity = ui.TextInput(
        label="Quantity",
        placeholder="Enter quantity...",
        min_length=1,
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get user's GrowID
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.followup.send("❌ Please set your GrowID first!", ephemeral=True)
                return

            # Validate product
            product = await self.product_manager.get_product(self.code.value.upper())
            if not product:
                await interaction.followup.send("❌ Invalid product code!", ephemeral=True)
                return

            # Validate quantity
            try:
                quantity = int(self.quantity.value)
                if quantity <= 0:
                    raise ValueError()
            except ValueError:
                await interaction.followup.send("❌ Invalid quantity!", ephemeral=True)
                return

            # Process purchase
            try:
                result = await self.trx_manager.process_purchase(
                    growid=growid,
                    product_code=self.code.value.upper(),
                    quantity=quantity
                )

                embed = discord.Embed(
                    title="✅ Purchase Successful",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="Product", value=f"`{product['name']}`", inline=True)
                embed.add_field(name="Quantity", value=str(quantity), inline=True)
                embed.add_field(name="Total Price", value=f"{result['total_price']:,} WL", inline=True)
                embed.add_field(name="New Balance", value=f"{result['new_balance']:,} WL", inline=False)

                content_msg = "**Your Items:**\n"
                for item in result['items']:
                    content_msg += f"```{item['content']}```\n"

                await interaction.followup.send(embed=embed, content=content_msg, ephemeral=True)

            except Exception as e:
                error_msg = str(e) if str(e) else "An error occurred during purchase"
                await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in BuyModal: {e}")
            await interaction.followup.send("❌ An error occurred", ephemeral=True)

class SetGrowIDModal(ui.Modal, title="Set GrowID"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger("SetGrowIDModal")
        self.balance_manager = BalanceManagerService(bot)

    growid = ui.TextInput(
        label="GrowID",
        placeholder="Enter your GrowID...",
        min_length=3,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            if await self.balance_manager.register_user(interaction.user.id, self.growid.value):
                embed = discord.Embed(
                    title="✅ GrowID Set Successfully",
                    description=f"Your GrowID has been set to: `{self.growid.value.upper()}`",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                self.logger.info(f"Set GrowID for Discord user {interaction.user.id} to {self.growid.value}")
            else:
                await interaction.followup.send("❌ Failed to set GrowID", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in SetGrowIDModal: {e}")
            await interaction.followup.send("❌ An error occurred", ephemeral=True)

class StockView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.balance_manager = BalanceManagerService(bot)
        self.product_manager = ProductManagerService(bot)
        self.trx_manager = TransactionManager(bot)
        self._cooldowns = {}
        self._interaction_locks = {}
        self.logger = logging.getLogger("StockView")
        self._init_buttons()
        self._cache_cleanup.start()

    def _init_buttons(self):
        self.add_item(Button(
            style=discord.ButtonStyle.primary,
            emoji="💰",
            label="Balance",
            custom_id="button_balance"
        ))
        self.add_item(Button(
            style=discord.ButtonStyle.success,
            emoji="🛒",
            label="Buy",
            custom_id="button_buy"
        ))
        self.add_item(Button(
            style=discord.ButtonStyle.secondary,
            emoji="🔑",
            label="Set GrowID",
            custom_id="button_set_growid"
        ))
        self.add_item(Button(
            style=discord.ButtonStyle.secondary,
            emoji="🔍",
            label="Check GrowID",
            custom_id="button_check_growid"
        ))
        self.add_item(Button(
            style=discord.ButtonStyle.secondary,
            emoji="🌍",
            label="World",
            custom_id="button_world"
        ))

    @tasks.loop(minutes=5)
    async def _cache_cleanup(self):
        """Cleanup expired cache entries"""
        current_time = time.time()
        self._cooldowns = {
            k: v for k, v in self._cooldowns.items()
            if current_time - v < COOLDOWN_SECONDS
        }
        self._interaction_locks = {
            k: v for k, v in self._interaction_locks.items()
            if current_time - v < 1.0
        }

    async def _check_cooldown(self, interaction: discord.Interaction) -> bool:
        user_id = interaction.user.id
        current_time = time.time()
        
        if user_id in self._cooldowns:
            remaining = COOLDOWN_SECONDS - (current_time - self._cooldowns[user_id])
            if remaining > 0:
                await interaction.response.send_message(
                    f"⏳ Please wait {remaining:.1f} seconds...",
                    ephemeral=True
                )
                return False
        
        self._cooldowns[user_id] = current_time
        return True

    async def _check_interaction_lock(self, interaction: discord.Interaction) -> bool:
        user_id = interaction.user.id
        current_time = time.time()
        
        if user_id in self._interaction_locks:
            if current_time - self._interaction_locks[user_id] < 1.0:
                return False
        
        self._interaction_locks[user_id] = current_time
        return True

    async def _safe_interaction_response(self, interaction: discord.Interaction, **kwargs):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(**kwargs)
            else:
                await interaction.followup.send(**kwargs)
        except Exception as e:
            self.logger.error(f"Error sending interaction response: {e}")

    @discord.ui.button(custom_id="button_balance")
    async def button_balance_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_cooldown(interaction) or not await self._check_interaction_lock(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.followup.send("❌ Please set your GrowID first!", ephemeral=True)
                return

            balance = await self.balance_manager.get_balance(growid)
            if not balance:
                await interaction.followup.send("❌ Balance not found!", ephemeral=True)
                return

            embed = discord.Embed(
                title="💰 Balance Information",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="GrowID", value=f"`{growid}`", inline=False)
            embed.add_field(name="Balance", value=balance.format(), inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in balance callback: {e}")
            await interaction.followup.send("❌ An error occurred", ephemeral=True)

    @discord.ui.button(custom_id="button_buy")
    async def button_buy_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_cooldown(interaction) or not await self._check_interaction_lock(interaction):
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
                content="❌ An error occurred",
                ephemeral=True
            )

    @discord.ui.button(custom_id="button_set_growid")
    async def button_set_growid_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_cooldown(interaction) or not await self._check_interaction_lock(interaction):
            return

        try:
            modal = SetGrowIDModal(self.bot)
            await interaction.response.send_modal(modal)

        except Exception as e:
            self.logger.error(f"Error in set growid callback: {e}")
            await self._safe_interaction_response(
                interaction,
                content="❌ An error occurred",
                ephemeral=True
            )

    @discord.ui.button(custom_id="button_check_growid")
    async def button_check_growid_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_cooldown(interaction) or not await self._check_interaction_lock(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            growid = await self.balance_manager.get_growid(interaction.user.id)
            if not growid:
                await interaction.followup.send("❌ You haven't set your GrowID yet!", ephemeral=True)
                return

            embed = discord.Embed(
                title="🔍 GrowID Information",
                description=f"Your registered GrowID: `{growid}`",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in check growid callback: {e}")
            await interaction.followup.send("❌ An error occurred", ephemeral=True)

    @discord.ui.button(custom_id="button_world")
    async def button_world_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_cooldown(interaction) or not await self._check_interaction_lock(interaction):
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            world_info = await self.product_manager.get_world_info()
            if not world_info:
                await interaction.followup.send("❌ World information not available.", ephemeral=True)
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
            
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in world callback: {e}")
            await interaction.followup.send("❌ An error occurred", ephemeral=True)

class LiveStock(commands.Cog):
    def __init__(self, bot):
        if not hasattr(bot, 'live_stock_instance'):
            self.bot = bot
            self.message_id = None
            self.update_lock = asyncio.Lock()
            self.last_update = datetime.utcnow().timestamp()
            self.service = LiveStockService(bot)
            self.stock_view = StockView(bot)
            self.logger = logging.getLogger("LiveStock")
            self._task = None
            
            bot.add_view(self.stock_view)
            self.live_stock.start()
            bot.live_stock_instance = self
            
            self.logger.info(f"LiveStock cog initialized at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    def cog_unload(self):
        if self._task:
            self._task.cancel()
        self.live_stock.cancel()

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def live_stock(self):
        async with self.update_lock:
            try:
                channel = self.bot.get_channel(int(self.bot.config['stock_channel_id']))
                if not channel:
                    return

                products = await self.service.product_manager.get_all_products()
                embed = await self.service.create_stock_embed(products)

                if self.message_id:
                    try:
                        message = await channel.fetch_message(self.message_id)
                        await message.edit(embed=embed)
                    except:
                        # Message not found, create new
                        message = await channel.send(embed=embed, view=self.stock_view)
                        self.message_id = message.id
                        self.logger.info(f"Created new stock message {self.message_id}")
                else:
                    # First time, create message
                    message = await channel.send(embed=embed, view=self.stock_view)
                    self.message_id = message.id
                    self.logger.info(f"Created initial message {self.message_id}")

                self.last_update = datetime.utcnow().timestamp()

            except Exception as e:
                self.logger.error(f"Error updating live stock: {e}")

    @live_stock.before_loop
    async def before_live_stock(self):
        await self.bot.wait_until_ready()

class LiveStockService:
    _instance = None

    def __new__(cls, bot):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self, bot):
        if not self.initialized:
            self.bot = bot
            self.logger = logging.getLogger("LiveStockService")
            self.product_manager = ProductManagerService(bot)
            self._cache = {}
            self._cache_timeout = CACHE_TIMEOUT
            self.initialized = True

    def _get_cached(self, key: str):
        if key in self._cache:
            data = self._cache[key]
            if time.time() - data['timestamp'] < self._cache_timeout:
                return data['value']
            del self._cache[key]
        return None

    def _set_cached(self, key: str, value):
        self._cache[key] = {
            'value': value,
            'timestamp': time.time()
        }

    async def create_stock_embed(self, products: list) -> discord.Embed:
        cache_key = f"stock_embed_{hash(str(products))}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        embed = discord.Embed(
            title="🏪 Store Stock Status",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        if products:
            for product in sorted(products, key=lambda x: x['code']):
                stock_count = await self.product_manager.get_stock_count(product['code'])
                value = (
                    f"💎 Code: `{product['code']}`\n"
                    f"📦 Stock: `{stock_count}`\n"
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
        
        self._set_cached(cache_key, embed)
        return embed

    async def cleanup(self):
        """Cleanup resources"""
        self._cache.clear()

async def setup(bot):
    """Setup the LiveStock cog"""
    if not hasattr(bot, 'live_stock_cog_loaded'):
        await bot.add_cog(LiveStock(bot))
        bot.live_stock_cog_loaded = True
        logging.info(f'LiveStock cog loaded successfully at {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC')