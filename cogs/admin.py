import discord
from discord.ext import commands
import logging
from datetime import datetime
import json
import asyncio
from typing import Optional, List
import io

from ext.constants import (
    CURRENCY_RATES,
    TRANSACTION_ADMIN_ADD,
    TRANSACTION_ADMIN_REMOVE,
    TRANSACTION_ADMIN_RESET,
    MAX_STOCK_FILE_SIZE,
    VALID_STOCK_FORMATS
)
from ext.balance_manager import BalanceManagerService
from ext.product_manager import ProductManagerService
from ext.trx import TransactionManager

class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("AdminCog")
        
        # Initialize services
        self.balance_service = BalanceManagerService(bot)
        self.product_service = ProductManagerService(bot)
        self.trx_manager = TransactionManager(bot)
        
        # Load admin configuration
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

    async def _process_stock_file(self, attachment) -> List[str]:
        """Process uploaded stock file"""
        if attachment.size > MAX_STOCK_FILE_SIZE:
            raise ValueError(f"File too large! Maximum size is {MAX_STOCK_FILE_SIZE/1024:.0f}KB")
            
        file_ext = attachment.filename.split('.')[-1].lower()
        if file_ext not in VALID_STOCK_FORMATS:
            raise ValueError(f"Invalid file format! Supported formats: {', '.join(VALID_STOCK_FORMATS)}")
            
        content = await attachment.read()
        text = content.decode('utf-8').strip()
        
        items = [line.strip() for line in text.split('\n') if line.strip()]
        if not items:
            raise ValueError("No valid items found in file!")
            
        return items

    async def _confirm_action(self, ctx, message: str, timeout: int = 30) -> bool:
        """Get confirmation for dangerous actions"""
        confirm_msg = await ctx.send(
            f"⚠️ **WARNING**\n{message}\nReact with ✅ to confirm or ❌ to cancel."
        )
        
        await confirm_msg.add_reaction('✅')
        await confirm_msg.add_reaction('❌')

        try:
            reaction, user = await self.bot.wait_for(
                'reaction_add',
                timeout=timeout,
                check=lambda r, u: u == ctx.author and str(r.emoji) in ['✅', '❌']
            )
            return str(reaction.emoji) == '✅'
        except asyncio.TimeoutError:
            await ctx.send("❌ Operation timed out!")
            return False

    @commands.command(name="adminhelp")
    async def admin_help(self, ctx):
        """Show admin commands"""
        if not await self._check_admin(ctx):
            return

        embed = discord.Embed(
            title="🛠️ Admin Commands",
            description="Available administrative commands",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        command_categories = {
            "Product Management": [
                "`addproduct <code> <name> <price> [description]`\nAdd new product",
                "`editproduct <code> <field> <value>`\nEdit product details",
                "`deleteproduct <code>`\nDelete product",
                "`addstock <code>`\nAdd stock with file attachment"
            ],
            "Balance Management": [
                "`addbal <growid> <amount> <WL/DL/BGL>`\nAdd balance",
                "`removebal <growid> <amount> <WL/DL/BGL>`\nRemove balance",
                "`checkbal <growid>`\nCheck balance",
                "`resetuser <growid>`\nReset balance"
            ],
            "Transaction Management": [
                "`trxhistory <growid> [limit]`\nView transactions",
                "`stockhistory <code> [limit]`\nView stock history"
            ]
        }

        for category, commands in command_categories.items():
            embed.add_field(
                name=f"📋 {category}",
                value="\n\n".join(commands),
                inline=False
            )

        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)
        @commands.command(name="addproduct")
        async def add_product(self, ctx, code: str, name: str, price: int, *, description: Optional[str] = None):
            """Add new product"""
            if not await self._check_admin(ctx):
                return
                
            try:
                result = await self.product_service.create_product(
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

    @commands.command(name="addstock")
    async def add_stock(self, ctx, code: str):
        """Add stock from file"""
        if not await self._check_admin(ctx):
            return
            
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach a text file containing the stock items!")
            return

        try:
            # Verify product exists
            product = await self.product_service.get_product(code.upper())
            if not product:
                await ctx.send(f"❌ Product code `{code}` not found!")
                return
            
            # Process stock file
            items = await self._process_stock_file(ctx.message.attachments[0])
            
            # Add stock with progress updates
            progress_msg = await ctx.send("⏳ Adding stock items...")
            added_count = 0
            failed_count = 0
            
            for i, item in enumerate(items, 1):
                try:
                    await self.product_service.add_stock_item(
                        code.upper(),
                        item,
                        str(ctx.author.id)
                    )
                    added_count += 1
                except:
                    failed_count += 1
                
                if i % 10 == 0:  # Update progress every 10 items
                    await progress_msg.edit(content=f"⏳ Processing... {i}/{len(items)} items")
            
            embed = discord.Embed(
                title="✅ Stock Added",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Product", value=f"{product['name']} ({code.upper()})", inline=False)
            embed.add_field(name="Total Items", value=len(items), inline=True)
            embed.add_field(name="Added", value=added_count, inline=True)
            embed.add_field(name="Failed", value=failed_count, inline=True)
            
            await progress_msg.delete()
            await ctx.send(embed=embed)
            self.logger.info(f"Stock added for {code} by {ctx.author}: {added_count} success, {failed_count} failed")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error adding stock: {e}")

    @commands.command(name="addbal")
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

            # Convert to appropriate currency
            wls = amount if currency == "WL" else amount * CURRENCY_RATES[currency]
            
            new_balance = await self.balance_service.update_balance(
                growid=growid.upper(),
                wl=wls,
                details=f"Added by admin {ctx.author}",
                transaction_type=TRANSACTION_ADMIN_ADD
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

    @commands.command(name="removebal")
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

            # Convert to WLs and make negative for removal
            wls = -(amount if currency == "WL" else amount * CURRENCY_RATES[currency])
            
            new_balance = await self.balance_service.update_balance(
                growid=growid.upper(),
                wl=wls,
                details=f"Removed by admin {ctx.author}",
                transaction_type=TRANSACTION_ADMIN_REMOVE
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
        @commands.command(name="checkbal")
        async def check_balance(self, ctx, growid: str):
            """Check user balance"""
            if not await self._check_admin(ctx):
                return
                
            try:
                balance = await self.balance_service.get_balance(growid.upper())
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
                        f"• {tx['type']} - {tx['timestamp']}: {tx['details']}"
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
            current_balance = await self.balance_service.get_balance(growid)
            if not current_balance:
                await ctx.send(f"❌ User {growid} not found!")
                return

            # Reset balance
            new_balance = await self.balance_service.update_balance(
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

    @commands.command(name="trxhistory")
    async def transaction_history(self, ctx, growid: str, limit: int = 10):
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

            message = await ctx.send(embed=pages[0])
            
            if len(pages) > 1:
                await message.add_reaction('⬅️')
                await message.add_reaction('➡️')

                current_page = 0

                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️']

                while True:
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                        if str(reaction.emoji) == '➡️':
                            current_page = (current_page + 1) % len(pages)
                        elif str(reaction.emoji) == '⬅️':
                            current_page = (current_page - 1) % len(pages)

                        await message.edit(embed=pages[current_page])
                        await message.remove_reaction(reaction, user)

                    except asyncio.TimeoutError:
                        await message.clear_reactions()
                        break

            self.logger.info(f"Transactions viewed for {growid} by {ctx.author}")
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
            self.logger.error(f"Error viewing transactions: {e}")

    @commands.command(name="stockhistory")
    async def stock_history(self, ctx, product_code: str, limit: int = 10):
        """View stock history for a product"""
        if not await self._check_admin(ctx):
            return
            
        try:
            product = await self.product_service.get_product(product_code.upper())
            if not product:
                await ctx.send(f"❌ Product code {product_code} not found!")
                return

            stock_items = await self.product_service.get_stock_history(
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

            message = await ctx.send(embed=pages[0])
            
            if len(pages) > 1:
                await message.add_reaction('⬅️')
                await message.add_reaction('➡️')

                current_page = 0

                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️']

                while True:
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                        if str(reaction.emoji) == '➡️':
                            current_page = (current_page + 1) % len(pages)
                        elif str(reaction.emoji) == '⬅️':
                            current_page = (current_page - 1) % len(pages)

                        await message.edit(embed=pages[current_page])
                        await message.remove_reaction(reaction, user)

                    except asyncio.TimeoutError:
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

            product = await self.product_service.get_product(code.upper())
            if not product:
                await ctx.send(f"❌ Product {code} not found!")
                return

            updated_product = await self.product_service.update_product(
                code=code.upper(),
                updates={field: value}
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
            product = await self.product_service.get_product(code.upper())
            if not product:
                await ctx.send(f"❌ Product {code} not found!")
                return

            success = await self.product_service.delete_product(code.upper())
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

async def setup(bot):
    """Setup the Admin cog"""
    if not hasattr(bot, 'admin_cog_loaded'):
        await bot.add_cog(AdminCog(bot))
        bot.admin_cog_loaded = True
        logging.info(f'Admin cog loaded successfully at {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC')