import discord
from discord.ext import commands
import logging
from datetime import datetime
import json
from asyncio import TimeoutError
from ext.constants import CURRENCY_RATES
from ext.balance_manager import BalanceManager
from ext.product_manager import ProductManager
from ext.trx import TransactionManager

class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot):
        self.bot = bot
        self._init_logger()
        # Initialize managers with bot instance
        self.balance_manager = BalanceManager(bot)
        self.product_manager = ProductManager(bot)
        self.trx_manager = TransactionManager(bot)
        
        print(f"Current Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Load admin ID from config.json
        try:
            with open('config.json') as f:
                config = json.load(f)
                self.admin_id = int(config['admin_id'])
                self.logger.info(f"Admin ID loaded: {self.admin_id}")
        except Exception as e:
            self.logger.error(f"Failed to load admin_id: {e}")
            raise

    def _init_logger(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def _check_admin(self, ctx):
        """Check if user has admin permissions"""
        is_admin = ctx.author.id == self.admin_id
        if not is_admin:
            await ctx.send("❌ You are not authorized to use admin commands!")
            self.logger.warning(f"Unauthorized access attempt by {ctx.author} (ID: {ctx.author.id})")
        else:
            self.logger.info(f"Admin command used by {ctx.author} (ID: {ctx.author.id})")
        return is_admin

    @commands.command(name="adminhelp")
    async def admin_help(self, ctx):
        """Show admin commands"""
        if not await self._check_admin(ctx):
            return

        embed = discord.Embed(
            title="Admin Commands",
            description="Available admin commands:",
            color=discord.Color.blue()
        )
        
        # Products Commands
        products_commands = [
            "`!addproduct <code> <name> <price> <description>` - Add a new product",
            "`!bulkstock [attach stock.txt]` - Add bulk stock from file",
            "`!editproduct <code> <field> <value>` - Edit product details",
            "`!deleteproduct <code>` - Delete a product"
        ]
        embed.add_field(
            name="Products",
            value="\n".join(products_commands),
            inline=False
        )
        
        # Balance Commands
        balance_commands = [
            "`!addbalance <growid> <amount> <currency>` - Add balance to user",
            "`!removebalance <growid> <amount> <currency>` - Remove balance from user",
            "`!checkbalance <growid>` - Check user balance",
            "`!resetuser <growid>` - Reset user balance",
            "`!transactions <growid> [limit]` - View transaction history"
        ]
        embed.add_field(
            name="Balance Management",
            value="\n".join(balance_commands),
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="addproduct")
    async def add_product(self, ctx, code: str, name: str, price: int, *, description: str = "No description"):
        """Add a new product"""
        if not await self._check_admin(ctx):
            return
            
        try:
            result = await self.product_manager.create_product(code, name, price, description)
            
            embed = discord.Embed(title="✅ Product Added", color=discord.Color.green())
            embed.add_field(name="Code", value=result['code'], inline=True)
            embed.add_field(name="Name", value=result['name'], inline=True)
            embed.add_field(name="Price", value=f"{result['price']:,} WLs", inline=True)
            embed.add_field(name="Description", value=result['description'], inline=False)
            
            await ctx.send(embed=embed)
            self.logger.info(f"Product {code} added by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error adding product: {e}")

    @commands.command(name="bulkstock")
    async def bulk_add_stock(self, ctx):
        """Add stock from attached file"""
        if not await self._check_admin(ctx):
            return

        if not ctx.message.attachments:
            embed = discord.Embed(
                title="❌ Missing File",
                description="Please attach a .txt file\n\n"
                          "Example usage:\n"
                          "1. Type `!bulkstock`\n"
                          "2. Attach any .txt file (stock.txt, items.txt, etc)\n"
                          "3. Send the message",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        try:
            # Process bulk stock using ProductManager
            embed, success = await self.product_manager.process_bulk_stock(
                ctx.message.attachments[0],
                ctx.author
            )
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error in bulk stock: {e}")

    @commands.command(name="editproduct")
    async def edit_product(self, ctx, code: str, field: str, *, value: str):
        """Edit product details"""
        if not await self._check_admin(ctx):
            return
            
        try:
            # Convert price to integer if editing price
            if field.lower() == 'price':
                try:
                    value = int(value)
                except ValueError:
                    await ctx.send("❌ Price must be a number!")
                    return

            # Update product using ProductManager
            result = await self.product_manager.update_product(code, **{field.lower(): value})
            
            embed = discord.Embed(title="✅ Product Updated", color=discord.Color.green())
            embed.add_field(name="Code", value=code, inline=True)
            embed.add_field(name="Field", value=field, inline=True)
            embed.add_field(name="New Value", value=str(value), inline=True)
            embed.set_footer(text=f"Updated by {ctx.author}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error editing product: {e}")

    @commands.command(name="deleteproduct")
    async def delete_product(self, ctx, code: str):
        """Delete a product"""
        if not await self._check_admin(ctx):
            return

        try:
            # Get product details first
            product = await self.product_manager.get_product(code)
            if not product:
                await ctx.send(f"❌ Product {code} not found!")
                return

            # Ask for confirmation
            confirm_msg = await ctx.send(
                f"⚠️ Are you sure you want to delete {code} ({product['name']})?\n"
                f"This action cannot be undone!"
            )
            await confirm_msg.add_reaction('✅')
            await confirm_msg.add_reaction('❌')

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ['✅', '❌']

            try:
                reaction, user = await self.bot.wait_for(
                    'reaction_add', 
                    timeout=30.0, 
                    check=check
                )
            except TimeoutError:
                await ctx.send("❌ Operation timed out!")
                return

            if str(reaction.emoji) == '❌':
                await ctx.send("❌ Operation cancelled!")
                return

            # Delete product using ProductManager
            await self.product_manager.delete_product(code)
            
            embed = discord.Embed(
                title="✅ Product Deleted",
                description=f"Product {code} ({product['name']}) has been deleted.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Deleted by {ctx.author}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error deleting product: {e}")

    @commands.command(name="addbalance")
    async def add_balance(self, ctx, growid: str, amount: int, currency: str):
        """Add balance to user"""
        if not await self._check_admin(ctx):
            return
            
        try:
            currency = currency.upper()
            if currency not in CURRENCY_RATES:
                await ctx.send(f"❌ Invalid currency. Use: {', '.join(CURRENCY_RATES.keys())}")
                return

            kwargs = {currency.lower(): amount}
            new_balance = await self.balance_manager.update_balance(
                growid,
                transaction_type="ADMIN_ADD",
                details=f"Added by admin {ctx.author}",
                **kwargs
            )

            embed = discord.Embed(title="✅ Balance Added", color=discord.Color.green())
            embed.add_field(name="GrowID", value=growid, inline=True)
            embed.add_field(name="Added", value=f"{amount:,} {currency}", inline=True)
            embed.add_field(name="New Balance", value=new_balance.format(), inline=False)
            embed.set_footer(text=f"Added by {ctx.author}")

            await ctx.send(embed=embed)
            self.logger.info(f"Balance added for user {growid}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error adding balance: {e}")

    @commands.command(name="removebalance")
    async def remove_balance(self, ctx, growid: str, amount: int, currency: str):
        """Remove balance from user"""
        if not await self._check_admin(ctx):
            return
            
        try:
            currency = currency.upper()
            if currency not in CURRENCY_RATES:
                await ctx.send(f"❌ Invalid currency. Use: {', '.join(CURRENCY_RATES.keys())}")
                return

            kwargs = {currency.lower(): -amount}
            new_balance = await self.balance_manager.update_balance(
                growid,
                transaction_type="ADMIN_REMOVE",
                details=f"Removed by admin {ctx.author}",
                **kwargs
            )

            embed = discord.Embed(title="✅ Balance Removed", color=discord.Color.red())
            embed.add_field(name="GrowID", value=growid, inline=True)
            embed.add_field(name="Removed", value=f"{amount:,} {currency}", inline=True)
            embed.add_field(name="New Balance", value=new_balance.format(), inline=False)
            embed.set_footer(text=f"Removed by {ctx.author}")

            await ctx.send(embed=embed)
            self.logger.info(f"Balance removed from user {growid}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error removing balance: {e}")

    @commands.command(name="checkbalance")
    async def check_balance(self, ctx, growid: str):
        """Check user balance"""
        if not await self._check_admin(ctx):
            return
            
        try:
            balance = await self.balance_manager.get_balance(growid)
            if not balance:
                await ctx.send(f"❌ User {growid} not found!")
                return

            embed = discord.Embed(title=f"Balance Check - {growid}", color=discord.Color.blue())
            embed.add_field(name="Balance", value=balance.format(), inline=False)
            embed.set_footer(text=f"Checked by {ctx.author}")

            await ctx.send(embed=embed)
            self.logger.info(f"Balance checked for user {growid}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error checking balance: {e}")

    @commands.command(name="resetuser")
    async def reset_user(self, ctx, growid: str):
        """Reset user balance to zero"""
        if not await self._check_admin(ctx):
            return

        try:
            # Check if user exists first
            if not await self.balance_manager.get_balance(growid):
                await ctx.send(f"❌ User {growid} not found!")
                return

            # Ask for confirmation
            confirm_msg = await ctx.send(
                f"⚠️ Are you sure you want to reset {growid}'s balance?\n"
                f"This action cannot be undone!"
            )
            await confirm_msg.add_reaction('✅')
            await confirm_msg.add_reaction('❌')

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ['✅', '❌']

            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            except TimeoutError:
                await ctx.send("❌ Operation timed out!")
                return

            if str(reaction.emoji) == '❌':
                await ctx.send("❌ Operation cancelled!")
                return

            # Reset balance using BalanceManager
            await self.balance_manager.reset_balance(growid, f"Reset by admin {ctx.author}")

            embed = discord.Embed(
                title="✅ User Reset",
                description=f"User {growid}'s balance has been reset to 0.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Reset by {ctx.author}")

            await ctx.send(embed=embed)
            self.logger.info(f"Balance reset for user {growid}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error resetting user: {e}")

    @commands.command(name="transactions")
    async def view_transactions(self, ctx, growid: str, limit: int = 10):
        """View transaction history"""
        if not await self._check_admin(ctx):
            return
            
        try:
            transactions = await self.trx_manager.get_transaction_history(growid, limit)
            if not transactions:
                await ctx.send(f"❌ No transactions found for {growid}")
                return

            embed = discord.Embed(
                title=f"Transaction History - {growid}", 
                color=discord.Color.blue()
            )
            
            for tx in transactions:
                embed.add_field(
                    name=f"{tx['type']} - {tx['timestamp']}",
                    value=f"Amount: {tx['amount']:,} {tx['currency']}\n"
                          f"Details: {tx['details']}",
                    inline=False
                )

            await ctx.send(embed=embed)
            self.logger.info(f"Transactions viewed for user {growid}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error viewing transactions: {e}")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))