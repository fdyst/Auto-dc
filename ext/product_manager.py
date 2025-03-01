import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from database import get_connection
from discord.ext import commands
from ext.constants import (
    STATUS_AVAILABLE, 
    STATUS_SOLD,
    TRANSACTION_PURCHASE,
    TRANSACTION_REFUND,
    TransactionError
)

class ProductManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._init_logger()
        
        # Import BalanceManager di sini untuk menghindari circular import
        from .balance_manager import BalanceManager
        
        # Inisialisasi dengan instance bot
        self.balance_manager = BalanceManager(self.bot)
        
        # Print initialization info
        print(f"Current Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Current User's Login: {self.bot.user}")

    def _init_logger(self):
        self.logger = logging.getLogger("ProductManager")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levellevel)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def create_product(self, code: str, name: str, price: int, description: Optional[str] = None) -> Dict:
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

    async def get_product(self, code: str) -> Optional[Dict]:
        """Get a product by code"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT code, name, price, description
                FROM products
                WHERE code = ?
            """, (code.upper(),))
            
            product = cursor.fetchone()
            if product:
                return {
                    'code': product[0],
                    'name': product[1],
                    'price': product[2],
                    'description': product[3]
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting product: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def get_all_products(self) -> List[Dict]:
        """Get all products"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT code, name, price, description
                FROM products
                ORDER BY name
            """)
            
            return [{
                'code': row[0],
                'name': row[1],
                'price': row[2],
                'description': row[3]
            } for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting all products: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def get_available_stock(self, product_code: str, quantity: int) -> List[Dict]:
        """Get available stock for a product"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, content
                FROM stock
                WHERE product_code = ?
                AND status = ?
                LIMIT ?
            """, (product_code.upper(), STATUS_AVAILABLE, quantity))
            
            return [{
                'id': row[0],
                'content': row[1]
            } for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting available stock: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def mark_stock_used(self, stock_id: int, buyer_id: str, seller_id: Optional[str] = None) -> bool:
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

async def setup(bot):
    await bot.add_cog(ProductManager(bot))