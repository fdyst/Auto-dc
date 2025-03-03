import discord
from discord.ext import commands
import logging
from datetime import datetime, timedelta
import asyncio
from typing import Optional

class Reputation(commands.Cog):
    """⭐ Sistem Reputasi"""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('Reputation')
        self.rep_cooldown = {}  # Cooldown tracking
        
    async def initialize_db(self):
        """Initialize database tables"""
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reputation (
                    user_id TEXT PRIMARY KEY,
                    points INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    total_received INTEGER DEFAULT 0,
                    total_given INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rep_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user TEXT NOT NULL,
                    to_user TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    reason TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def calculate_level(self, points: int) -> int:
        """Calculate level based on points"""
        if points < 100:
            return 1
        elif points < 500:
            return 2
        elif points < 1000:
            return 3
        elif points < 2500:
            return 4
        else:
            return 5

    @commands.command(name="rep+", aliases=["+rep"])
    @commands.cooldown(1, 3600, commands.BucketType.user)  # 1 hour cooldown
    async def rep_plus(self, ctx, member: discord.Member, *, reason: str = None):
        """⭐ Tambah reputasi ke member"""
        if member.id == ctx.author.id:
            return await ctx.send("❌ Anda tidak bisa memberi reputasi ke diri sendiri!")

        async with self.bot.pool.acquire() as conn:
            # Check if recipient exists in database
            await conn.execute("""
                INSERT OR IGNORE INTO reputation (user_id) VALUES (?)
            """, (str(member.id),))
            
            # Update reputation
            await conn.execute("""
                UPDATE reputation 
                SET points = points + 1,
                    total_received = total_received + 1,
                    level = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (self.calculate_level(await self.get_points(member.id) + 1), str(member.id)))
            
            # Update giver's stats
            await conn.execute("""
                UPDATE reputation 
                SET total_given = total_given + 1
                WHERE user_id = ?
            """, (str(ctx.author.id),))
            
            # Log the reputation change
            await conn.execute("""
                INSERT INTO rep_history (from_user, to_user, amount, reason)
                VALUES (?, ?, 1, ?)
            """, (str(ctx.author.id), str(member.id), reason))

        embed = discord.Embed(
            title="⭐ Reputasi Ditambahkan",
            description=f"{ctx.author.mention} memberi reputasi ke {member.mention}",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        if reason:
            embed.add_field(name="Alasan", value=reason)
            
        user_rep = await self.get_reputation(member.id)
        embed.add_field(
            name="Status Reputasi",
            value=f"Level: {user_rep['level']}\nPoin: {user_rep['points']}"
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="rep-", aliases=["-rep"])
    @commands.has_permissions(manage_messages=True)  # Hanya moderator
    async def rep_minus(self, ctx, member: discord.Member, *, reason: str = None):
        """⭐ Kurangi reputasi member (Moderator only)"""
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                UPDATE reputation 
                SET points = MAX(0, points - 1),
                    level = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (self.calculate_level(await self.get_points(member.id) - 1), str(member.id)))
            
            await conn.execute("""
                INSERT INTO rep_history (from_user, to_user, amount, reason)
                VALUES (?, ?, -1, ?)
            """, (str(ctx.author.id), str(member.id), f"[MOD] {reason}" if reason else "[MOD] No reason provided"))

        embed = discord.Embed(
            title="⚠️ Reputasi Dikurangi",
            description=f"Moderator {ctx.author.mention} mengurangi reputasi {member.mention}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        if reason:
            embed.add_field(name="Alasan", value=reason)
            
        user_rep = await self.get_reputation(member.id)
        embed.add_field(
            name="Status Reputasi",
            value=f"Level: {user_rep['level']}\nPoin: {user_rep['points']}"
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="reputation", aliases=["rep"])
    async def check_reputation(self, ctx, member: Optional[discord.Member] = None):
        """📊 Cek reputasi member"""
        target = member or ctx.author
        rep_data = await self.get_reputation(target.id)
        
        embed = discord.Embed(
            title="📊 Profil Reputasi",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        # Main stats
        embed.add_field(
            name="Status",
            value=f"Level: {rep_data['level']}\n"
                  f"Poin: {rep_data['points']}\n"
                  f"Rank: {await self.get_rank(target.id)}",
            inline=False
        )
        
        # Additional stats
        embed.add_field(
            name="Statistik",
            value=f"Total Diterima: {rep_data['total_received']}\n"
                  f"Total Diberikan: {rep_data['total_given']}",
            inline=False
        )
        
        # Recent history
        history = await self.get_recent_history(target.id)
        if history:
            recent_changes = "\n".join([
                f"{'➕' if h['amount'] > 0 else '➖'} dari {self.bot.get_user(int(h['from_user'])).name}"
                for h in history[:3]
            ])
            embed.add_field(name="Riwayat Terakhir", value=recent_changes, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name="toprep")
    async def reputation_leaderboard(self, ctx):
        """🏆 Tampilkan leaderboard reputasi"""
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, points, level 
                FROM reputation 
                ORDER BY points DESC 
                LIMIT 10
            """)

        if not rows:
            return await ctx.send("❌ Belum ada data reputasi!")

        embed = discord.Embed(
            title="🏆 Leaderboard Reputasi",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        for idx, row in enumerate(rows, 1):
            user = self.bot.get_user(int(row['user_id']))
            if user:
                embed.add_field(
                    name=f"#{idx} {user.name}",
                    value=f"Level {row['level']} | {row['points']} poin",
                    inline=False
                )

        await ctx.send(embed=embed)

    async def get_reputation(self, user_id: int) -> dict:
        """Get user's reputation data"""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM reputation WHERE user_id = ?
            """, (str(user_id),))
            
            if not row:
                await conn.execute("""
                    INSERT INTO reputation (user_id) VALUES (?)
                """, (str(user_id),))
                return {
                    'points': 0,
                    'level': 1,
                    'total_received': 0,
                    'total_given': 0
                }
            
            return dict(row)

    async def get_points(self, user_id: int) -> int:
        """Get user's reputation points"""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT points FROM reputation WHERE user_id = ?
            """, (str(user_id),))
            return row['points'] if row else 0

    async def get_rank(self, user_id: int) -> int:
        """Get user's rank position"""
        async with self.bot.pool.acquire() as conn:
            rank = await conn.fetchval("""
                SELECT COUNT(*) + 1 
                FROM reputation 
                WHERE points > (
                    SELECT points 
                    FROM reputation 
                    WHERE user_id = ?
                )
            """, (str(user_id),))
            return rank

    async def get_recent_history(self, user_id: str, limit: int = 3):
        """Get recent reputation history"""
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM rep_history 
                WHERE to_user = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (str(user_id), limit))
            return rows

async def setup(bot):
    reputation_cog = Reputation(bot)
    await reputation_cog.initialize_db()
    await bot.add_cog(reputation_cog)