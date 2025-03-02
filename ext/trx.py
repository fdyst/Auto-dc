import logging
import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime

import discord
from discord.ext import commands

from .constants import STATUS_AVAILABLE, STATUS_SOLD, TransactionError
from database import get_connection

class TransactionManager:
    _instance = None

    def __new__(cls, bot):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self, bot):
        if not self.initialized:
            self.bot = bot
            self.logger = logging.getLogger("TransactionManager")
            self._cache = {}
            self._cache_timeout = 30
            self._locks = {}
            self.initialized = True

    # ... (kode TransactionManager yang sama seperti sebelumnya) ...
    async def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def process_purchase(self, growid: str, product_code: str, quantity: int = 1) -> Optional[Dict]:
        async with await self._get_lock(f"purchase_{growid}_{product_code}"):
            conn = None
            try:
                conn = get_connection()
                cursor = conn.cursor()
                
                # Get product details
                cursor.execute(
                    "SELECT price FROM products WHERE code = ?",
                    (product_code.upper(),)
                )
                product = cursor.fetchone()
                if not product:
                    raise TransactionError(f"Product {product_code} not found")
                
                total_price = product['price'] * quantity
                
                # Get available stock
                cursor.execute("""
                    SELECT id, content 
                    FROM stock 
                    WHERE product_code = ? AND status = ?
                    ORDER BY added_at ASC
                    LIMIT ?
                """, (product_code.upper(), STATUS_AVAILABLE, quantity))
                
                stock_items = cursor.fetchall()
                if len(stock_items) < quantity:
                    raise TransactionError(f"Insufficient stock for {product_code}")
                
                # Get user balance
                cursor.execute(
                    "SELECT balance_wl FROM users WHERE growid = ?",
                    (growid.upper(),)
                )
                user = cursor.fetchone()
                if not user:
                    raise TransactionError(f"User {growid} not found")
                
                if user['balance_wl'] < total_price:
                    raise TransactionError("Insufficient balance")
                
                # Update stock status
                stock_ids = [item['id'] for item in stock_items]
                cursor.execute(f"""
                    UPDATE stock 
                    SET status = ?, buyer_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id IN ({','.join('?' * len(stock_ids))})
                """, [STATUS_SOLD, growid.upper()] + stock_ids)
                
                # Update user balance
                new_balance = user['balance_wl'] - total_price
                cursor.execute(
                    "UPDATE users SET balance_wl = ? WHERE growid = ?",
                    (new_balance, growid.upper())
                )
                
                # Record transaction
                cursor.execute(
                    """
                    INSERT INTO transactions 
                    (growid, type, details, old_balance, new_balance, items_count, total_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        growid.upper(),
                        'PURCHASE',
                        f"Purchased {quantity} {product_code}",
                        str(user['balance_wl']) + " WL",
                        str(new_balance) + " WL",
                        quantity,
                        total_price
                    )
                )
                
                conn.commit()
                
                return {
                    'success': True,
                    'items': [dict(item) for item in stock_items],
                    'total_price': total_price,
                    'new_balance': new_balance
                }

            except Exception as e:
                self.logger.error(f"Error processing purchase: {e}")
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()

    async def get_transaction_history(self, growid: str, limit: int = 10) -> List[Dict]:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE growid = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (growid.upper(), limit))
            
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting transaction history: {e}")
            return []
        finally:
            if conn:
                conn.close()

    async def get_stock_history(self, product_code: str, limit: int = 10) -> List[Dict]:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM stock 
                WHERE product_code = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (product_code.upper(), limit))
            
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting stock history: {e}")
            return []
        finally:
            if conn:
                conn.close()

    async def cleanup(self):
        """Cleanup resources"""
        self._cache.clear()
        self._locks.clear()
        
class TransactionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trx_manager = TransactionManager(bot)
        self.logger = logging.getLogger("TransactionCog")

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info(f"TransactionCog is ready at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

async def setup(bot):
    """Setup the Transaction cog"""
    if not hasattr(bot, 'transaction_cog_loaded'):
        await bot.add_cog(TransactionCog(bot))
        bot.transaction_cog_loaded = True
        logging.info(f'Transaction cog loaded successfully at {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC')
