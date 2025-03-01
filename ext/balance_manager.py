import discord
import logging
from datetime import datetime
from typing import Optional, Dict
from database import get_connection
from .constants import CURRENCY_RATES
from discord.ext import commands

class Balance:
    def __init__(self, wl: int = 0, dl: int = 0, bgl: int = 0):
        self.wl = wl
        self.dl = dl
        self.bgl = bgl

    @property
    def total_wls(self) -> int:
        return self.wl + (self.dl * 100) + (self.bgl * 10000)

    def format(self) -> str:
        return (
            f"💎 BGLs: {self.bgl:,}\n"
            f"💜 DLs: {self.dl:,}\n"
            f"💚 WLs: {self.wl:,}\n"
            f"Total in WLs: {self.total_wls:,}"
        )

class BalanceManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._init_logger()
        self._cache = {}

    def _init_logger(self):
        self.logger = logging.getLogger("BalanceManager")
        self.logger.setLevel(logging.INFO)

    async def register_user(self, user_id: int, growid: str) -> bool:
        """Register or update user's GrowID"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Check if GrowID is already registered
            cursor.execute(
                "SELECT user_id FROM users WHERE growid = ? AND user_id != ?",
                (growid.upper(), user_id)
            )
            if cursor.fetchone():
                return False

            # Insert or update user with initial balance
            cursor.execute("""
                INSERT OR REPLACE INTO users 
                (user_id, growid, balance_wl, balance_dl, balance_bgl, created_at)
                VALUES (?, ?, 0, 0, 0, CURRENT_TIMESTAMP)
            """, (user_id, growid.upper()))

            conn.commit()
            self.logger.info(f"Registered user {user_id} with GrowID {growid}")
            return True

        except Exception as e:
            self.logger.error(f"Error registering user: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    async def get_growid(self, user_id: int) -> Optional[str]:
        """Get user's GrowID"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT growid FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            return result[0] if result else None

        except Exception as e:
            self.logger.error(f"Error getting GrowID: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def get_balance(self, growid: str) -> Optional[Balance]:
        """Get user balance"""
        if growid in self._cache:
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
                balance = Balance(result[0], result[1], result[2])
                self._cache[growid] = balance
                return balance
            return None

        except Exception as e:
            self.logger.error(f"Error getting balance: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def update_balance(self, growid: str, wl: int = 0, dl: int = 0, bgl: int = 0,
                           details: str = "", transaction_type: str = "UPDATE") -> Balance:
        """Update user balance"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get and validate current balance
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl 
                FROM users WHERE growid = ?
            """, (growid.upper(),))
            
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"User {growid} not found")

            old_balance = Balance(result[0], result[1], result[2])
            new_balance = Balance(
                old_balance.wl + wl,
                old_balance.dl + dl,
                old_balance.bgl + bgl
            )

            if new_balance.wl < 0 or new_balance.dl < 0 or new_balance.bgl < 0:
                raise ValueError("Insufficient balance")

            # Update balance
            cursor.execute("""
                UPDATE users 
                SET balance_wl = ?, balance_dl = ?, balance_bgl = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE growid = ?
            """, (new_balance.wl, new_balance.dl, new_balance.bgl, growid.upper()))

            # Log transaction
            cursor.execute("""
                INSERT INTO transactions 
                (growid, type, details, old_balance, new_balance, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                growid.upper(), 
                transaction_type,
                details,
                old_balance.format(),
                new_balance.format()
            ))

            conn.commit()
            self._cache[growid] = new_balance
            return new_balance

        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error updating balance: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def clear_cache(self, growid: str = None):
        """Clear balance cache"""
        if growid:
            self._cache.pop(growid, None)
        else:
            self._cache.clear()

    async def has_growid(self, user_id: int) -> bool:
        """Check if user has registered GrowID"""
        try:
            growid = await self.get_growid(user_id)
            return growid is not None
        except Exception as e:
            self.logger.error(f"Error checking GrowID: {e}")
            return False

async def setup(bot):
    await bot.add_cog(BalanceManager(bot))