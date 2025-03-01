import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple
from database import get_connection
from discord.ext import commands
from ext.constants import (
    STATUS_AVAILABLE, 
    STATUS_SOLD,
    TRANSACTION_PURCHASE,
    TRANSACTION_REFUND
)

class TransactionManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._init_logger()
        
        # Import BalanceManager dan ProductManager di sini untuk menghindari circular import
        from .balance_manager import BalanceManager
        from .product_manager import ProductManager
        
        # Inisialisasi dengan instance bot
        self.balance_manager = BalanceManager(self.bot)
        self.product_manager = ProductManager(self.bot)
        
        # Print initialization info
        print(f"Current Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Current User's Login: {self.bot.user}")

    def _init_logger(self):
        self.logger = logging.getLogger("TransactionManager")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def process_purchase(self, user_id: int, product_code: str, 
                             quantity: int, growid: str) -> Tuple[bool, str, List[str]]:
        """
        Process a purchase transaction
        Returns: (success, message, items)
        """
        conn = None
        total_price = 0
        name = ""
        try:
            # Log purchase attempt
            self.logger.info(f"Purchase attempt - User: {user_id}, GrowID: {growid}, Product: {product_code}, Quantity: {quantity}")
            
            conn = get_connection()
            cursor = conn.cursor()

            # Get product details with proper status check
            cursor.execute("""
                SELECT p.code, p.name, p.price, 
                       (SELECT COUNT(*) FROM stock s 
                        WHERE s.product_code = p.code 
                        AND s.status = ?) as stock
                FROM products p 
                WHERE p.code = ?
            """, (STATUS_AVAILABLE, product_code))

            product = cursor.fetchone()
            if not product:
                self.logger.warning(f"Product not found: {product_code}")
                return False, "Product not found", []

            code, name, price, stock = product
            self.logger.info(f"Product found - Name: {name}, Price: {price}, Stock: {stock}")

            if stock < quantity:
                self.logger.warning(f"Insufficient stock - Required: {quantity}, Available: {stock}")
                return False, f"Insufficient stock ({stock} available)", []

            total_price = price * quantity

            # Get current balance
            balance = await self.balance_manager.get_balance(growid)
            if not balance:
                self.logger.warning(f"Balance not found for GrowID: {growid}")
                return False, "Could not get your balance", []

            self.logger.info(f"Current balance for {growid}: {balance.format()}")

            # Check if enough balance
            if balance.total_wls < total_price:
                self.logger.warning(f"Insufficient balance - Required: {total_price}, Available: {balance.total_wls}")
                return False, f"Insufficient balance. Need {total_price:,} WLs", []

            # Get available stock
            available_stock = await self.product_manager.get_available_stock(code, quantity)
            if len(available_stock) < quantity:
                self.logger.warning(f"Stock not available - Required: {quantity}, Available: {len(available_stock)}")
                return False, "Stock not available", []

            # Update balance
            try:
                new_balance = await self.balance_manager.update_balance(
                    growid,
                    wl=-total_price,
                    details=f"Purchase: {name} x{quantity}",
                    transaction_type=TRANSACTION_PURCHASE
                )
                self.logger.info(f"Balance updated - New balance: {new_balance.format()}")
            except ValueError as e:
                self.logger.error(f"Balance update failed: {e}")
                return False, str(e), []

            # Mark stock as used with transaction tracking
            items = []
            transaction_time = datetime.utcnow()
            
            for stock_item in available_stock:
                success = await self.product_manager.mark_stock_used(
                    stock_item['id'], 
                    buyer_id=growid,
                    seller_id=str(user_id)
                )
                if not success:
                    raise Exception(f"Failed to mark stock {stock_item['id']} as used")
                items.append(stock_item['content'])

            # Record transaction details
            cursor.execute("""
                INSERT INTO transactions (
                    growid, type, details, old_balance, new_balance, 
                    items_count, total_price, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                growid, 
                TRANSACTION_PURCHASE,
                f"Purchase: {name} x{quantity}",
                str(balance.format()),
                str((balance.total_wls - total_price)),
                quantity,
                total_price,
                transaction_time
            ))

            # Create success message
            success_msg = (
                f"Successfully purchased {quantity}x {name}\n"
                f"Total Price: {total_price:,} WLs\n"
                f"Items will be sent via DM"
            )

            conn.commit()
            self.logger.info(
                f"Purchase successful - User: {user_id}, GrowID: {growid}, "
                f"Product: {name}, Quantity: {quantity}, Price: {total_price} WLs"
            )
            return True, success_msg, items

        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error processing purchase: {e}", exc_info=True)
            # Try to refund if balance was deducted
            try:
                if total_price > 0:
                    await self.balance_manager.update_balance(
                        growid,
                        wl=total_price,
                        details=f"Refund: Failed purchase of {name} x{quantity}",
                        transaction_type=TRANSACTION_REFUND
                    )
                    self.logger.info(f"Refund processed for {growid}: {total_price} WLs")
            except Exception as refund_error:
                self.logger.error(f"Failed to process refund: {refund_error}", exc_info=True)
            raise

        finally:
            if conn:
                conn.close()

    async def get_world_info(self) -> Optional[Dict]:
        """Get world information"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT world, owner, bot, updated_at 
                FROM world_info 
                WHERE id = 1
            """)
            result = cursor.fetchone()
            
            if result:
                return {
                    'world': result[0],
                    'owner': result[1],
                    'bot': result[2],
                    'last_updated': result[3]
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting world info: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def update_world_info(self, world: str, owner: str = None, bot: str = None) -> bool:
        """Update world information"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE world_info 
                SET world = ?, owner = ?, bot = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (world.upper(), owner, bot))
            
            conn.commit()
            return True

        except Exception as e:
            self.logger.error(f"Error updating world info: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    async def mark_stock_used(self, stock_id: int, buyer_id: str, seller_id: str = None) -> bool:
        """Mark stock as used"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE stock
                SET status = ?, 
                    buyer_id = ?,
                    seller_id = ?
                WHERE id = ? AND status = ?
            """, (STATUS_SOLD, buyer_id, seller_id, stock_id, STATUS_AVAILABLE))
            
            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            self.logger.error(f"Error marking stock used: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    async def process_bulk_stock(self, product_code: str, attachment, author) -> tuple:
        """Process bulk stock upload for specified product code"""
        try:
            # Verify product exists
            product = await self.get_product(product_code.upper())
            if not product:
                return discord.Embed(
                    title="❌ Product Not Found",
                    description=f"Product code `{product_code}` not found!",
                    color=discord.Color.red()
                ), False

            # Read file content
            stock_content = await attachment.read()
            stock_text = stock_content.decode('utf-8')
        
            # Split into lines and remove empty lines
            lines = [line.strip() for line in stock_text.split('\n') if line.strip()]
        
            if not lines:
                return discord.Embed(
                    title="❌ Empty File",
                    description="The file is empty!",
                    color=discord.Color.red()
                ), False

            successful = 0
            failed = 0
            
            for i, line in enumerate(lines, 1):
                try:
                    # Get only the first part before | as content
                    content = line.split('|')[0].strip()
                    
                    if not content:
                        failed += 1
                        continue

                    # Add stock using the add_stock method
                    if await self.add_stock(
                        product_code=product_code.upper(),
                        content=content,
                        added_by=str(author),
                        line_number=i
                    ):
                        successful += 1
                    else:
                        failed += 1

                except Exception as e:
                    self.logger.error(f"Error processing line {i}: {e}")
                    failed += 1
                    continue
            
            embed = discord.Embed(
                title="✅ Stock Processing Complete",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(
                name="Product Code",
                value=f"`{product_code.upper()}`",
                inline=False
            )
            embed.add_field(
                name="Results",
                value=f"✅ Added: {successful}\n❌ Failed: {failed}",
                inline=False
            )
            
            return embed, True
                    
        except Exception as e:
            self.logger.error(f"Error processing bulk stock: {e}")
            embed = discord.Embed(
                title="❌ Error Processing File",
                description=str(e),
                color=discord.Color.red()
            )
            return embed, False

    async def create_product(self, code: str, name: str, price: int, description: str = None) -> Dict:
        """Create a new product"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO products (code, name, price, description)
                VALUES (?, ?, ?, ?)
            """, (code.upper(), name, price, description))
            
            conn.commit()
            
            return {
                'code': code.upper(),
                'name': name,
                'price': price,
                'description': description
            }

        except sqlite3.IntegrityError:
            raise ValueError(f"Product code {code} already exists!")
        except Exception as e:
            self.logger.error(f"Error creating product: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

async def setup(bot):
    try:
        await bot.add_cog(ProductManager(bot))
        logging.info("ProductManager cog loaded successfully")
    except Exception as e:
        logging.error(f"Error loading ProductManager cog: {e}")