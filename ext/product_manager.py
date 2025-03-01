import discord
import logging
import sqlite3
from typing import List, Dict, Optional
from database import get_connection
from discord.ext import commands
from ext.constants import STATUS_AVAILABLE, STATUS_SOLD

class ProductManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._init_logger()
        self._cache = {}

    def _init_logger(self):
        self.logger = logging.getLogger("ProductManager")
        self.logger.setLevel(logging.INFO)

    async def get_all_products(self) -> List[Dict]:
        """Get all available products"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT p.code, p.name, p.price, p.description,
                       (SELECT COUNT(*) FROM stock s 
                        WHERE s.product_code = p.code 
                        AND s.status = ?) as stock
                FROM products p
                ORDER BY p.name ASC
            """, (STATUS_AVAILABLE,))
            
            products = []
            for row in cursor.fetchall():
                products.append({
                    'code': row[0],
                    'name': row[1],
                    'price': row[2],
                    'description': row[3],
                    'stock': row[4]
                })
                
            return products

        except Exception as e:
            self.logger.error(f"Error getting products: {e}")
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
                SET world = ?, owner = ?, bot = ?
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

    async def process_bulk_stock(self, attachment, author) -> tuple:
        """Process bulk stock from file"""
        try:
            stock_content = await attachment.read()
            stock_text = stock_content.decode('utf-8')
            
            lines = [line.strip() for line in stock_text.split('\n') if line.strip()]
            
            if not lines:
                return discord.Embed(
                    title="❌ Empty File",
                    description="The file is empty!",
                    color=discord.Color.red()
                ), False

            conn = get_connection()
            cursor = conn.cursor()
            
            try:
                successful = 0
                failed = 0
                
                for i, line in enumerate(lines, 1):
                    try:
                        cursor.execute("""
                            INSERT INTO stock (content, status, added_by, line_number)
                            VALUES (?, ?, ?, ?)
                        """, (line, STATUS_AVAILABLE, str(author), i))
                        successful += 1
                    except sqlite3.IntegrityError:
                        failed += 1
                        continue
                
                conn.commit()
                
                embed = discord.Embed(
                    title="✅ Stock Processing Complete",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(
                    name="Results",
                    value=f"✅ Added: {successful}\n❌ Failed: {failed}",
                    inline=False
                )
                return embed, True
                
            except Exception as e:
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()
                
        except Exception as e:
            self.logger.error(f"Error processing bulk stock: {e}")
            embed = discord.Embed(
                title="❌ Error Processing File",
                description=str(e),
                color=discord.Color.red()
            )
            return embed, False

async def setup(bot):
    await bot.add_cog(ProductManager(bot))