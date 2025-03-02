import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from database import get_connection
from discord.ext import commands
from .constants import (
    STATUS_AVAILABLE, 
    STATUS_SOLD,
    TRANSACTION_PURCHASE,
    TRANSACTION_REFUND,
    TransactionError,
    Balance
)

class TransactionManager:
    """Manager class for handling transactions"""
    _instance = None

    def __new__(cls, bot):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, bot):
        if not hasattr(self, 'initialized'):
            self.bot = bot
            self.logger = logging.getLogger("TransactionManager")
            
            # Import managers here to avoid circular imports
            from .balance_manager import BalanceManager
            from .product_manager import ProductManager
            
            self.balance_manager = BalanceManager(bot)
            self.product_manager = ProductManager(bot)
            self.initialized = True

    async def process_purchase(
        self, 
        discord_id: int, 
        product_code: str, 
        quantity: int
    ) -> Tuple[bool, str, List[str]]:
        """Process a purchase transaction"""
        conn = None
        try:
            # Get user's GrowID
            growid = await self.balance_manager.get_growid(discord_id)
            if not growid:
                return False, "You need to set your GrowID first!", []

            # Get product details
            product = await self.product_manager.get_product(product_code)
            if not product:
                return False, "Product not found", []

            total_price = product['price'] * quantity

            # Check stock availability
            available_stock = await self.product_manager.get_available_stock(
                product_code, 
                quantity
            )
            if len(available_stock) < quantity:
                return False, f"Insufficient stock ({len(available_stock)} available)", []

            # Get and check balance
            balance = await self.balance_manager.get_balance(growid)
            if not balance:
                return False, "Could not get your balance", []

            if balance.total_wls < total_price:
                return False, f"Insufficient balance (need {total_price:,} WLs)", []

            # Begin purchase process
            conn = get_connection()
            conn.execute("BEGIN TRANSACTION")

            # Update balance
            try:
                new_balance = await self.balance_manager.update_balance(
                    growid,
                    wl=-total_price,
                    details=f"Purchase: {product['name']} x{quantity}",
                    transaction_type=TRANSACTION_PURCHASE
                )
            except ValueError as e:
                return False, str(e), []

            # Mark items as sold
            items = []
            for stock in available_stock[:quantity]:
                success = await self.product_manager.mark_stock_used(
                    stock['id'],
                    buyer_id=growid,
                    seller_id=str(discord_id)
                )
                if not success:
                    raise TransactionError(f"Failed to mark stock {stock['id']} as used")
                items.append(stock['content'])

            # Record transaction details
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (
                    growid, type, details, old_balance, new_balance,
                    items_count, total_price, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                growid,
                TRANSACTION_PURCHASE,
                f"Purchase: {product['name']} x{quantity}",
                balance.format(),
                new_balance.format(),
                quantity,
                total_price
            ))

            conn.commit()

            success_msg = (
                f"✅ Purchase successful!\n"
                f"Product: {product['name']} x{quantity}\n"
                f"Total Price: {total_price:,} WLs\n"
                f"New Balance: {new_balance.format()}\n"
                f"Items will be sent via DM"
            )

            return True, success_msg, items

        except TransactionError as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Transaction error: {e}")
            return False, str(e), []

        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error processing purchase: {e}")
            return False, "An error occurred during purchase", []

        finally:
            if conn:
                conn.close()

    async def get_transaction_history(
        self, 
        growid: str, 
        limit: int = 10
    ) -> List[Dict]:
        """Get transaction history for a user"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    id,
                    type,
                    details,
                    old_balance,
                    new_balance,
                    items_count,
                    total_price,
                    created_at
                FROM transactions
                WHERE growid = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (growid.upper(), limit))

            return [{
                'id': row['id'],
                'type': row['type'],
                'details': row['details'],
                'old_balance': row['old_balance'],
                'new_balance': row['new_balance'],
                'items_count': row['items_count'],
                'total_price': row['total_price'],
                'created_at': datetime.strptime(
                    row['created_at'], 
                    '%Y-%m-%d %H:%M:%S'
                ).strftime('%Y-%m-%d %H:%M')
            } for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting transaction history: {e}")
            raise
        finally:
            if conn:
                conn.close()

class Transaction(commands.Cog):
    """Cog for transaction commands"""
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("Transaction")
        self._task = None
        self.manager = TransactionManager(bot)

        # Flag untuk mencegah duplikasi
        if not hasattr(bot, 'transaction_initialized'):
            bot.transaction_initialized = True
            self.logger.info("Transaction cog initialized")

    def cog_unload(self):
        """Cleanup saat unload"""
        if self._task and not self._task.done():
            self._task.cancel()
        self.logger.info("Transaction cog unloaded")

async def setup(bot):
    """Setup the Transaction cog"""
    if not hasattr(bot, 'transaction_cog_loaded'):
        await bot.add_cog(Transaction(bot))
        bot.transaction_cog_loaded = True
        logging.info('Transaction cog loaded successfully')