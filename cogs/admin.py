import discord
from discord.ext import commands
import logging
from datetime import datetime
import json
from asyncio import TimeoutError
from typing import Optional

from ext.constants import (
    CURRENCY_RATES,
    TRANSACTION_ADMIN_ADD,
    TRANSACTION_ADMIN_REMOVE,
    TRANSACTION_ADMIN_RESET
)
from ext.balance_manager import BalanceManager
from ext.product_manager import ProductManager
from ext.trx import TransactionManager

class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("AdminCog")
        
        # Initialize managers
        self.balance_manager = BalanceManager(bot)
        self.product_manager = ProductManager(bot)
        self.trx_manager = TransactionManager(bot)
        
        # Load admin ID from config
        try:
            with open('config.json') as f:
                config = json.load(f)
                self.admin_id = int(config['admin_id'])
                self.logger.info(f"Admin ID loaded: {self.admin_id}")
        except Exception as e:
            self.logger.error(f"Failed to load admin_id: {e}")
            raise

    async def _check_admin(self, ctx) -> bool:
        """Check if user has admin permissions"""
        is_admin = ctx.author.id == self.admin_id
        if not is_admin:
            await ctx.send("❌ You don't have permission to use admin commands!")
            self.logger.warning(f"Unauthorized access attempt by {ctx.author} (ID: {ctx.author.id})")
        return is_admin

    # Di dalam command admin_help
    @commands.command(name="adminhelp")
    async def admin_help(self, ctx):
        """Show admin commands"""
        if not await self._check_admin(ctx):
            return
    
        # Buat single embed dengan multiple fields
        embed = discord.Embed(
            title="🛠️ Admin Commands",
            description="List of available admin commands",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
    
        # Organize commands by category
        command_categories = {
            "Product Management": [
                "`!addproduct <code> <name> <price> [description]`\nAdd a new product",
                "`!editproduct <code> <field> <value>`\nEdit product details",
                "`!deleteproduct <code>`\nDelete a product",
                "`!bulkstock <code>`\nAdd bulk stock from file"
            ],
            "Balance Management": [
                "`!addbalance <growid> <amount> <WL/DL/BGL>`\nAdd balance to user",
                "`!removebalance <growid> <amount> <WL/DL/BGL>`\nRemove balance from user",
                "`!checkbalance <growid>`\nCheck user balance",
                "`!resetuser <growid>`\nReset user balance"
            ],
            "Transaction Management": [
                "`!transactions <growid> [limit]`\nView transaction history",
                "`!stockhistory <product_code> [limit]`\nView stock history"
            ]
        }
    
        # Add each category as a field
        for category, commands in command_categories.items():
            embed.add_field(
                name=f"📋 {category}",
                value="\n\n".join(commands),
                inline=False
            )
    
        embed.set_footer(text=f"Requested by {ctx.author}")
        
        # Send single embed
        await ctx.send(embed=embed)

    @commands.command(name="addproduct")
    async def add_product(self, ctx, code: str, name: str, price: int, *, description: Optional[str] = None):
        """Add a new product"""
        if not await self._check_admin(ctx):
            return
            
        try:
            result = await self.product_manager.create_product(
                code=code,
                name=name,
                price=price,
                description=description
            )
            
            embed = discord.Embed(
                title="✅ Product Added",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Code", value=result['code'], inline=True)
            embed.add_field(name="Name", value=result['name'], inline=True)
            embed.add_field(name="Price", value=f"{result['price']:,} WLs", inline=True)
            if result['description']:
                embed.add_field(name="Description", value=result['description'], inline=False)
            
            await ctx.send(embed=embed)
            self.logger.info(f"Product {code} added by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error adding product: {e}")

    @commands.command(name="bulkstock")
    async def bulk_stock(self, ctx, product_code: str):
        """Add bulk stock from file"""
        if not await self._check_admin(ctx):
            return
            
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach a text file containing the stock items!")
            return
    
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith('.txt'):
            await ctx.send("❌ Please attach a .txt file!")
            return
    
        try:
            # Verify product exists
            product = await self.product_manager.get_product(product_code)
            if not product:
                await ctx.send(f"❌ Product code `{product_code}` not found!")
                return
            
            # Read and process file
            stock_content = await attachment.read()
            stock_text = stock_content.decode('utf-8')
            items = [line.strip() for line in stock_text.split('\n') if line.strip()]
            
            if not items:
                await ctx.send("❌ No valid items found in file!")
                return
            
            # Add stock items
            added_count = await self.product_manager.add_stock(
                product_code=product_code,
                contents=items,
                added_by=str(ctx.author)
            )
            
            embed = discord.Embed(
                title="✅ Stock Added Successfully",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Product", value=product['name'], inline=True)
            embed.add_field(name="Code", value=product_code.upper(), inline=True)
            embed.add_field(
                name="Results",
                value=f"✅ Added: {added_count}\n❌ Failed: {len(items) - added_count}",
                inline=False
            )
            
            await ctx.send(embed=embed)
            self.logger.info(f"Bulk stock added for {product_code} by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error adding bulk stock: {e}")

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

            if amount <= 0:
                await ctx.send("❌ Amount must be positive!")
                return

            # Convert amount to appropriate currency field
            kwargs = {
                "wl": amount if currency == "WL" else 0,
                "dl": amount if currency == "DL" else 0,
                "bgl": amount if currency == "BGL" else 0,
                "details": f"Balance added by admin {ctx.author}",
                "transaction_type": TRANSACTION_ADMIN_ADD
            }

            new_balance = await self.balance_manager.update_balance(
                growid=growid.upper(),
                **kwargs
            )

            embed = discord.Embed(
                title="✅ Balance Added",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="GrowID", value=growid.upper(), inline=True)
            embed.add_field(name="Added", value=f"{amount:,} {currency}", inline=True)
            embed.add_field(name="New Balance", value=new_balance.format(), inline=False)
            embed.set_footer(text=f"Added by {ctx.author}")

            await ctx.send(embed=embed)
            self.logger.info(f"Balance added for {growid} by {ctx.author}")
            
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

            if amount <= 0:
                await ctx.send("❌ Amount must be positive!")
                return

            # Convert to negative for removal
            kwargs = {
                "wl": -amount if currency == "WL" else 0,
                "dl": -amount if currency == "DL" else 0,
                "bgl": -amount if currency == "BGL" else 0,
                "details": f"Balance removed by admin {ctx.author}",
                "transaction_type": TRANSACTION_ADMIN_REMOVE
            }

            new_balance = await self.balance_manager.update_balance(
                growid=growid.upper(),
                **kwargs
            )

            embed = discord.Embed(
                title="✅ Balance Removed",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="GrowID", value=growid.upper(), inline=True)
            embed.add_field(name="Removed", value=f"{amount:,} {currency}", inline=True)
            embed.add_field(name="New Balance", value=new_balance.format(), inline=False)
            embed.set_footer(text=f"Removed by {ctx.author}")

            await ctx.send(embed=embed)
            self.logger.info(f"Balance removed from {growid} by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error removing balance: {e}")

    @commands.command(name="checkbalance")
    async def check_balance(self, ctx, growid: str):
        """Check user balance"""
        if not await self._check_admin(ctx):
            return
            
        try:
            balance = await self.balance_manager.get_balance(growid.upper())
            if not balance:
                await ctx.send(f"❌ User {growid} not found!")
                return

            transactions = await self.trx_manager.get_transaction_history(growid.upper(), limit=5)

            embed = discord.Embed(
                title=f"👤 User Information - {growid.upper()}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Current Balance", value=balance.format(), inline=False)
            
            if transactions:
                recent_tx = "\n".join([
                    f"{tx['type']} - {tx['timestamp']}: {tx['details']}"
                    for tx in transactions
                ])
                embed.add_field(name="Recent Transactions", value=recent_tx, inline=False)

            embed.set_footer(text=f"Checked by {ctx.author}")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error checking balance: {e}")

    @commands.command(name="resetuser")
    async def reset_user(self, ctx, growid: str):
        """Reset user balance"""
        if not await self._check_admin(ctx):
            return

        try:
            growid = growid.upper()
            current_balance = await self.balance_manager.get_balance(growid)
            if not current_balance:
                await ctx.send(f"❌ User {growid} not found!")
                return

            confirm_msg = await ctx.send(
                f"⚠️ **WARNING**\nAre you sure you want to reset {growid}'s balance?\n"
                f"Current balance: {current_balance.format()}\n"
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

            # Reset balance
            new_balance = await self.balance_manager.update_balance(
                growid=growid,
                wl=-current_balance.wl,
                dl=-current_balance.dl,
                bgl=-current_balance.bgl,
                details=f"Balance reset by admin {ctx.author}",
                transaction_type=TRANSACTION_ADMIN_RESET
            )

            embed = discord.Embed(
                title="✅ Balance Reset",
                description=f"User {growid}'s balance has been reset.",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Previous Balance", value=current_balance.format(), inline=False)
            embed.add_field(name="New Balance", value=new_balance.format(), inline=False)
            embed.set_footer(text=f"Reset by {ctx.author}")

            await ctx.send(embed=embed)
            self.logger.info(f"Balance reset for {growid} by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error resetting user: {e}")

    @commands.command(name="transactions")
    async def view_transactions(self, ctx, growid: str, limit: int = 10):
        """View transaction history"""
        if not await self._check_admin(ctx):
            return
            
        try:
            growid = growid.upper()
            transactions = await self.trx_manager.get_transaction_history(growid, limit)
            if not transactions:
                await ctx.send(f"❌ No transactions found for {growid}")
                return

            pages = []
            items_per_page = 5
            
            for i in range(0, len(transactions), items_per_page):
                embed = discord.Embed(
                    title=f"Transaction History - {growid}",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                
                page_transactions = transactions[i:i + items_per_page]
                for tx in page_transactions:
                    value = (
                        f"Type: {tx['type']}\n"
                        f"Details: {tx['details']}\n"
                        f"Old Balance: {tx['old_balance']}\n"
                        f"New Balance: {tx['new_balance']}\n"
                        f"Items: {tx['items_count'] if tx.get('items_count') else 'N/A'}\n"
                        f"Total Price: {tx['total_price']:,} WLs" if tx.get('total_price') else "Total Price: N/A\n"
                        f"Time: {tx['created_at']}"
                    )
                    embed.add_field(
                        name=f"Transaction #{tx['id']}", 
                        value=value,
                        inline=False
                    )
                
                embed.set_footer(text=f"Page {i//items_per_page + 1}/{(len(transactions)-1)//items_per_page + 1}")
                pages.append(embed)

            # Send first page
            message = await ctx.send(embed=pages[0])
            
            # Add navigation reactions if more than one page
            if len(pages) > 1:
                await message.add_reaction('⬅️')
                await message.add_reaction('➡️')

                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️']

                current_page = 0
                while True:
                    try:
                        reaction, user = await self.bot.wait_for(
                            'reaction_add',
                            timeout=60.0,
                            check=check
                        )

                        if str(reaction.emoji) == '➡️':
                            current_page = (current_page + 1) % len(pages)
                        elif str(reaction.emoji) == '⬅️':
                            current_page = (current_page - 1) % len(pages)

                        await message.edit(embed=pages[current_page])
                        await message.remove_reaction(reaction, user)

                    except TimeoutError:
                        await message.clear_reactions()
                        break

            self.logger.info(f"Transactions viewed for {growid} by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error viewing transactions: {e}")

    @commands.command(name="stockhistory")
    async def view_stock_history(self, ctx, product_code: str, limit: int = 10):
        """View stock history for a product"""
        if not await self._check_admin(ctx):
            return
            
        try:
            product = await self.product_manager.get_product(product_code.upper())
            if not product:
                await ctx.send(f"❌ Product code {product_code} not found!")
                return

            stock_items = await self.product_manager.get_stock_history(
                product_code=product_code.upper(),
                limit=limit
            )

            if not stock_items:
                await ctx.send(f"❌ No stock history found for {product_code}")
                return

            pages = []
            items_per_page = 5

            for i in range(0, len(stock_items), items_per_page):
                embed = discord.Embed(
                    title=f"Stock History - {product['name']} ({product_code.upper()})",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )

                page_items = stock_items[i:i + items_per_page]
                for item in page_items:
                    value = (
                        f"Status: {item['status']}\n"
                        f"Added by: {item['added_by']}\n"
                        f"Added at: {item['added_at']}\n"
                        f"Buyer: {item['buyer_id'] if item['buyer_id'] else 'N/A'}\n"
                        f"Used at: {item['used_at'] if item['used_at'] else 'N/A'}"
                    )
                    embed.add_field(
                        name=f"Stock #{item['id']}", 
                        value=value,
                        inline=False
                    )

                embed.set_footer(text=f"Page {i//items_per_page + 1}/{(len(stock_items)-1)//items_per_page + 1}")
                pages.append(embed)

            # Send first page
            message = await ctx.send(embed=pages[0])
            
            # Add navigation reactions if more than one page
            if len(pages) > 1:
                await message.add_reaction('⬅️')
                await message.add_reaction('➡️')

                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️']

                current_page = 0
                while True:
                    try:
                        reaction, user = await self.bot.wait_for(
                            'reaction_add',
                            timeout=60.0,
                            check=check
                        )

                        if str(reaction.emoji) == '➡️':
                            current_page = (current_page + 1) % len(pages)
                        elif str(reaction.emoji) == '⬅️':
                            current_page = (current_page - 1) % len(pages)

                        await message.edit(embed=pages[current_page])
                        await message.remove_reaction(reaction, user)

                    except TimeoutError:
                        await message.clear_reactions()
                        break

            self.logger.info(f"Stock history viewed for {product_code} by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error viewing stock history: {e}")

    @commands.command(name="editproduct")
    async def edit_product(self, ctx, code: str, field: str, *, value: str):
        """Edit product details"""
        if not await self._check_admin(ctx):
            return
            
        try:
            field = field.lower()
            if field not in ['name', 'price', 'description']:
                await ctx.send("❌ Valid fields are: name, price, description")
                return

            if field == 'price':
                try:
                    value = int(value)
                    if value <= 0:
                        await ctx.send("❌ Price must be positive!")
                        return
                except ValueError:
                    await ctx.send("❌ Price must be a number!")
                    return

            product = await self.product_manager.get_product(code.upper())
            if not product:
                await ctx.send(f"❌ Product {code} not found!")
                return

            # Update product
            updated_product = await self.product_manager.update_product(
                code=code.upper(),
                field=field,
                value=value
            )

            embed = discord.Embed(
                title="✅ Product Updated",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Code", value=updated_product['code'], inline=True)
            embed.add_field(name="Name", value=updated_product['name'], inline=True)
            embed.add_field(name="Price", value=f"{updated_product['price']:,} WLs", inline=True)
            if updated_product['description']:
                embed.add_field(name="Description", value=updated_product['description'], inline=False)
            
            await ctx.send(embed=embed)
            self.logger.info(f"Product {code} updated by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error editing product: {e}")

    @commands.command(name="deleteproduct")
    async def delete_product(self, ctx, code: str):
        """Delete a product"""
        if not await self._check_admin(ctx):
            return

        try:
            product = await self.product_manager.get_product(code.upper())
            if not product:
                await ctx.send(f"❌ Product {code} not found!")
                return

            # Ask for confirmation
            confirm_msg = await ctx.send(
                f"⚠️ Are you sure you want to delete product {product['name']} ({code.upper()})?\n"
                f"This will also delete all associated stock items!\n"
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

            # Delete product
            success = await self.product_manager.delete_product(code.upper())
            if not success:
                await ctx.send("❌ Failed to delete product!")
                return

            embed = discord.Embed(
                title="✅ Product Deleted",
                description=f"Product {product['name']} ({code.upper()}) has been deleted.",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Deleted by {ctx.author}")
            
            await ctx.send(embed=embed)
            self.logger.info(f"Product {code} deleted by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error deleting product: {e}")

# Di bagian paling bawah file
async def setup(bot):
    """Setup the Admin cog"""
    if not hasattr(bot, 'admin_cog_loaded'):  # Check if already loaded
        await bot.add_cog(AdminCog(bot))
        bot.admin_cog_loaded = True
        logging.info('Admin cog loaded successfully')