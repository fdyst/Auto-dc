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
        return self.wl + (self.dl * CURRENCY_RATES['DL']) + (self.bgl * CURRENCY_RATES['BGL'])

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
        self.logger = logging.getLogger("BalanceManager")
        self._cache = {}

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
            return result['growid'] if result else None

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
                balance = Balance(
                    result['balance_wl'],
                    result['balance_dl'],
                    result['balance_bgl']
                )
                self._cache[growid] = balance
                return balance
            return None

        except Exception as e:
            self.logger.error(f"Error getting balance: {e}")
            raise
        finally:
            if conn:
                conn.close()

    async def update_balance(
        self, growid: str, 
        wl: int = 0, dl: int = 0, bgl: int = 0,
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

    async def has_growid(self, discord_id: int) -> bool:
        """Check if user has registered GrowID"""
        try:
            growid = await self.get_growid(discord_id)
            return growid is not None
        except Exception as e:
            self.logger.error(f"Error checking GrowID: {e}")
            return False

async def setup(bot):
    await bot.add_cog(BalanceManager(bot))