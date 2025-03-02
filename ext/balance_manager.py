import discord
import logging
from datetime import datetime
from typing import Optional, Dict
from database import get_connection
from discord.ext import commands
from .constants import Balance, CURRENCY_RATES

class BalanceManagerService:
    """Service class for handling balance operations"""
    _instance = None

    def __new__(cls, bot):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, bot):
        if not hasattr(self, 'initialized'):
            self.bot = bot
            self.logger = logging.getLogger("BalanceManagerService")
            self._cache = {}
            self.initialized = True
            self.logger.info("BalanceManagerService initialized")

    def clear_cache(self, growid: str = None):
        """Clear balance cache"""
        if growid:
            self._cache.pop(growid, None)
            self.logger.debug(f"Cleared cache for GrowID: {growid}")
        else:
            self._cache.clear()
            self.logger.debug("Cleared all cache")

    async def register_user(self, discord_id: int, growid: str) -> bool:
        """Register or update user's GrowID"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Begin transaction
            conn.execute("BEGIN TRANSACTION")
            
            # First ensure user exists in users table
            cursor.execute("""
                INSERT OR IGNORE INTO users (growid)
                VALUES (?)
            """, (growid.upper(),))
            
            # Then map Discord ID to GrowID
            cursor.execute("""
                INSERT OR REPLACE INTO user_growid (discord_id, growid)
                VALUES (?, ?)
            """, (str(discord_id), growid.upper()))
            
            conn.commit()
            # Clear cache for this user
            self.clear_cache(growid.upper())
            self.logger.info(f"Registered Discord user {discord_id} with GrowID {growid}")
            return True

        except Exception as e:
            self.logger.error(f"Error registering user: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    async def get_growid(self, discord_id: int) -> Optional[str]:
        """Get user's GrowID"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT growid FROM user_growid 
                WHERE discord_id = ?
            """, (str(discord_id),))
            
            result = cursor.fetchone()
            if result:
                self.logger.info(f"Found GrowID for Discord ID {discord_id}: {result['growid']}")
            else:
                self.logger.info(f"No GrowID found for Discord ID {discord_id}")
                
            return result['growid'] if result else None

        except Exception as e:
            self.logger.error(f"Error getting GrowID: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def has_growid(self, discord_id: int) -> bool:
        """Check if user has registered GrowID"""
        growid = await self.get_growid(discord_id)
        return growid is not None

    async def get_balance(self, growid: str) -> Optional[Balance]:
        """Get user balance"""
        if growid in self._cache:
            self.logger.debug(f"Retrieved balance from cache for GrowID: {growid}")
            return self._cache[growid]

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl 
                FROM users WHERE growid = ?
            """, (growid.upper(),))
            
            result = cursor.fetchone()
            if result:
                balance = Balance(
                    result['balance_wl'],
                    result['balance_dl'],
                    result['balance_bgl']
                )
                self._cache[growid] = balance
                self.logger.debug(f"Retrieved and cached balance for GrowID: {growid}")
                return balance
            
            self.logger.info(f"No balance found for GrowID: {growid}")
            return None

        except Exception as e:
            self.logger.error(f"Error getting balance: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def update_balance(
        self, 
        growid: str, 
        wl: int = 0, 
        dl: int = 0, 
        bgl: int = 0,
        details: str = "", 
        transaction_type: str = "UPDATE"
    ) -> Balance:
        """Update user balance"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Begin transaction
            conn.execute("BEGIN TRANSACTION")

            # Get current balance
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl 
                FROM users WHERE growid = ?
            """, (growid.upper(),))
            
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"User {growid} not found")

            old_balance = Balance(
                result['balance_wl'],
                result['balance_dl'],
                result['balance_bgl']
            )
            
            new_balance = Balance(
                old_balance.wl + wl,
                old_balance.dl + dl,
                old_balance.bgl + bgl
            )

            if new_balance.total_wls < 0:
                raise ValueError("Insufficient balance")

            # Update balance
            cursor.execute("""
                UPDATE users 
                SET balance_wl = ?, 
                    balance_dl = ?, 
                    balance_bgl = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE growid = ?
            """, (new_balance.wl, new_balance.dl, new_balance.bgl, growid.upper()))

            # Log transaction
            cursor.execute("""
                INSERT INTO transactions 
                (growid, type, details, old_balance, new_balance)
                VALUES (?, ?, ?, ?, ?)
            """, (
                growid.upper(), 
                transaction_type,
                details,
                old_balance.format(),
                new_balance.format()
            ))

            conn.commit()
            # Update cache
            self._cache[growid] = new_balance
            self.logger.info(f"Updated balance for {growid}: {old_balance.format()} -> {new_balance.format()}")
            return new_balance

        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error updating balance: {e}")
            raise
        finally:
            if conn:
                conn.close()

class BalanceManager(commands.Cog):
    """Cog for balance management commands"""
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("BalanceManager")
        self._task = None
        self.manager = BalanceManagerService(bot)

        # Flag untuk mencegah duplikasi
        if not hasattr(bot, 'balance_manager_initialized'):
            bot.balance_manager_initialized = True
            self.logger.info("BalanceManager cog initialized")

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self._task and not self._task.done():
            self._task.cancel()
        # Clear cache on unload
        if hasattr(self, 'manager'):
            self.manager.clear_cache()
        self.logger.info("BalanceManager cog unloaded")
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Handler for when bot is ready"""
        # Clear cache on bot ready
        if hasattr(self, 'manager'):
            self.manager.clear_cache()
        self.logger.info("BalanceManager is ready")

async def setup(bot):
    """Setup the BalanceManager cog"""
    if not hasattr(bot, 'balance_manager_loaded'):
        await bot.add_cog(BalanceManager(bot))
        bot.balance_manager_loaded = True
        logging.info('BalanceManager cog loaded successfully')