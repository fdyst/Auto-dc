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

    async def get_recent_transactions(self, growid: str, limit: int = 5) -> List[Dict]:
        """Get recent transactions for a user"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    type, 
                    details, 
                    created_at,
                    items_count,
                    total_price
                FROM transactions
                WHERE growid = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (growid, limit))

            return [{
                'type': row[0],
                'details': row[1],
                'created_at': datetime.strptime(
                    row[2], '%Y-%m-%d %H:%M:%S'
                ).strftime('%Y-%m-%d %H:%M'),
                'items_count': row[3],
                'total_price': row[4]
            } for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting transactions: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def get_transaction_history(self, growid: str, limit: int = 10) -> List[Dict]:
        """Get detailed transaction history"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    type, 
                    old_balance, 
                    new_balance, 
                    details, 
                    created_at,
                    items_count,
                    total_price
                FROM transactions
                WHERE growid = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (growid, limit))

            return [{
                'type': row[0],
                'old_balance': row[1],
                'new_balance': row[2],
                'details': row[3],
                'timestamp': datetime.strptime(
                    row[4], '%Y-%m-%d %H:%M:%S'
                ).strftime('%Y-%m-%d %H:%M'),
                'items_count': row[5],
                'total_price': row[6]
            } for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting transaction history: {e}")
            raise
        finally:
            if conn:
                conn.close()

async def setup(bot):
    await bot.add_cog(TransactionManager(bot))