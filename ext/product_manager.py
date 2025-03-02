import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from database import get_connection
from discord.ext import commands
from .constants import STATUS_AVAILABLE, STATUS_SOLD

class ProductManagerService:
    """Service class for handling product operations"""
    _instance = None

    def __new__(cls, bot):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, bot):
        if not hasattr(self, 'initialized'):
            self.bot = bot
            self.logger = logging.getLogger("ProductManagerService")
            self.initialized = True

    async def create_product(
        self, 
        code: str, 
        name: str, 
        price: int, 
        description: Optional[str] = None
    ) -> Dict:
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
                SELECT p.code, p.name, p.price, p.description,
                       (SELECT COUNT(*) FROM stock s 
                        WHERE s.product_code = p.code 
                        AND s.status = ?) as stock_count
                FROM products p
                WHERE p.code = ?
            """, (STATUS_AVAILABLE, code.upper()))
            
            product = cursor.fetchone()
            if product:
                return {
                    'code': product['code'],
                    'name': product['name'],
                    'price': product['price'],
                    'description': product['description'],
                    'stock': product['stock_count']
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting product: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def get_all_products(self) -> List[Dict]:
        """Get all products with their stock count"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT p.code, p.name, p.price, p.description,
                       (SELECT COUNT(*) FROM stock s 
                        WHERE s.product_code = p.code 
                        AND s.status = ?) as stock_count
                FROM products p
                ORDER BY p.name
            """, (STATUS_AVAILABLE,))
            
            return [{
                'code': row['code'],
                'name': row['name'],
                'price': row['price'],
                'description': row['description'],
                'stock': row['stock_count']
            } for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting all products: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def get_available_stock(
        self, 
        product_code: str, 
        quantity: int
    ) -> List[Dict]:
        """Get available stock for a product"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, content, added_at
                FROM stock
                WHERE product_code = ?
                AND status = ?
                ORDER BY added_at ASC
                LIMIT ?
            """, (product_code.upper(), STATUS_AVAILABLE, quantity))
            
            return [{
                'id': row['id'],
                'content': row['content'],
                'added_at': row['added_at']
            } for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error getting available stock: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def add_stock(
        self, 
        product_code: str, 
        contents: List[str], 
        added_by: str
    ) -> int:
        """Add stock items for a product"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Check if product exists
            cursor.execute(
                "SELECT code FROM products WHERE code = ?", 
                (product_code.upper(),)
            )
            if not cursor.fetchone():
                raise ValueError(f"Product {product_code} does not exist")

            # Begin transaction
            conn.execute("BEGIN TRANSACTION")
            
            added_count = 0
            for content in contents:
                try:
                    cursor.execute("""
                        INSERT INTO stock 
                        (product_code, content, added_by, status)
                        VALUES (?, ?, ?, ?)
                    """, (product_code.upper(), content.strip(), added_by, STATUS_AVAILABLE))
                    added_count += 1
                except sqlite3.IntegrityError:
                    self.logger.warning(f"Duplicate stock content: {content}")
                    continue

            conn.commit()
            return added_count

        except Exception as e:
            self.logger.error(f"Error adding stock: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    async def mark_stock_used(
        self, 
        stock_id: int, 
        buyer_id: str, 
        seller_id: Optional[str] = None
    ) -> bool:
        """Mark stock as used"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                UPDATE stock
                SET status = ?, 
                    buyer_id = ?,
                    seller_id = ?,
                    used_at = ?
                WHERE id = ? AND status = ?
            """, (STATUS_SOLD, buyer_id, seller_id, current_time, stock_id, STATUS_AVAILABLE))
            
            conn.commit()
            success = cursor.rowcount > 0
            
            if success:
                self.logger.info(
                    f"Stock {stock_id} marked as sold to {buyer_id}"
                    + (f" by {seller_id}" if seller_id else "")
                )
            else:
                self.logger.warning(f"Failed to mark stock {stock_id} as used")
                
            return success

        except Exception as e:
            self.logger.error(f"Error marking stock used: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    async def get_stock_info(self, stock_id: int) -> Optional[Dict]:
        """Get detailed information about a stock item"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, p.name as product_name, p.price
                FROM stock s
                JOIN products p ON s.product_code = p.code
                WHERE s.id = ?
            """, (stock_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row['id'],
                    'product_code': row['product_code'],
                    'product_name': row['product_name'],
                    'content': row['content'],
                    'status': row['status'],
                    'price': row['price'],
                    'buyer_id': row['buyer_id'],
                    'seller_id': row['seller_id'],
                    'added_by': row['added_by'],
                    'added_at': row['added_at'],
                    'used_at': row['used_at']
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting stock info: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def delete_product(self, code: str) -> bool:
        """Delete a product and its stock"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Begin transaction
            conn.execute("BEGIN TRANSACTION")
            
            # Delete product (cascade will handle stock)
            cursor.execute(
                "DELETE FROM products WHERE code = ?", 
                (code.upper(),)
            )
            
            success = cursor.rowcount > 0
            if success:
                conn.commit()
                self.logger.info(f"Product {code} deleted successfully")
            else:
                conn.rollback()
                self.logger.warning(f"Product {code} not found")
            
            return success

        except Exception as e:
            self.logger.error(f"Error deleting product: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    async def update_product(
        self, 
        code: str, 
        updates: Dict
    ) -> bool:
        """Update product details"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Prepare update query
            update_fields = []
            params = []
            for key, value in updates.items():
                if key in ['name', 'price', 'description']:
                    update_fields.append(f"{key} = ?")
                    params.append(value)

            if not update_fields:
                return False

            # Add product code to params
            params.append(code.upper())

            # Execute update
            query = f"""
                UPDATE products 
                SET {', '.join(update_fields)}
                WHERE code = ?
            """
            cursor.execute(query, params)
            
            success = cursor.rowcount > 0
            if success:
                conn.commit()
                self.logger.info(f"Product {code} updated successfully")
            else:
                conn.rollback()
                self.logger.warning(f"Product {code} not found")

            return success

        except Exception as e:
            self.logger.error(f"Error updating product: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

class ProductManager(commands.Cog):
    """Cog for product management commands"""
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("ProductManager")
        self._task = None
        self.manager = ProductManagerService(bot)

        # Flag untuk mencegah duplikasi
        if not hasattr(bot, 'product_manager_initialized'):
            bot.product_manager_initialized = True
            self.logger.info("ProductManager cog initialized")

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self._task and not self._task.done():
            self._task.cancel()
        self.logger.info("ProductManager cog unloaded")

    @commands.Cog.listener()
    async def on_ready(self):
        """Handler for when bot is ready"""
        self.logger.info("ProductManager is ready")

async def setup(bot):
    """Setup the ProductManager cog"""
    if not hasattr(bot, 'product_manager_loaded'):
        await bot.add_cog(ProductManager(bot))
        bot.product_manager_loaded = True
        logging.info('ProductManager cog loaded successfully')