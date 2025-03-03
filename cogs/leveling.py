import discord
from discord.ext import commands
import random
from datetime import datetime
import asyncio

class Leveling(commands.Cog):
    """📊 Sistem Level"""
    
    def __init__(self, bot):
        self.bot = bot
        self.xp_cooldown = {}
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        # Check cooldown
        if not self.can_gain_xp(message.author.id):
            return
            
        # Give random XP
        xp = random.randint(15, 25)
        await self.add_xp(message.author.id, xp)
        
        # Check for level up
        old_level = await self.get_level(message.author.id)
        new_level = await self.calculate_level(message.author.id)
        
        if new_level > old_level:
            embed = discord.Embed(
                title="🎉 Level Up!",
                description=f"{message.author.mention} telah naik ke level {new_level}!",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            await message.channel.send(embed=embed)
            
    def can_gain_xp(self, user_id: int) -> bool:
        if user_id not in self.xp_cooldown:
            self.xp_cooldown[user_id] = datetime.utcnow()
            return True
            
        diff = datetime.utcnow() - self.xp_cooldown[user_id]
        if diff.total_seconds() >= 60:  # 1 minute cooldown
            self.xp_cooldown[user_id] = datetime.utcnow()
            return True
        return False
        
    async def add_xp(self, user_id: int, xp: int):
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO levels (user_id, xp)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                xp = xp + ?
            """, (str(user_id), xp, xp))
            
    async def calculate_level(self, user_id: int) -> int:
        xp = await self.get_xp(user_id)
        return int((xp / 100) ** 0.5)
        
    async def get_xp(self, user_id: int) -> int:
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchone("""
                SELECT xp FROM levels WHERE user_id = ?
            """, (str(user_id),))
            return row['xp'] if row else 0
            
    async def get_level(self, user_id: int) -> int:
        xp = await self.get_xp(user_id)
        return int((xp / 100) ** 0.5)
        
    @commands.command(name="rank")
    async def show_rank(self, ctx, member: discord.Member = None):
        """Lihat rank member"""
        target = member or ctx.author
        
        xp = await self.get_xp(target.id)
        level = await self.get_level(target.id)
        rank = await self.get_rank(target.id)
        
        # Calculate progress to next level
        next_level_xp = (level + 1) ** 2 * 100
        current_level_xp = level ** 2 * 100
        xp_needed = next_level_xp - current_level_xp
        xp_progress = xp - current_level_xp
        progress = (xp_progress / xp_needed) * 100
        
        embed = discord.Embed(
            title="📊 Rank Card",
            color=target.color,
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(
            name="Level",
            value=f"```{level}```",
            inline=True
        )
        embed.add_field(
            name="Rank",
            value=f"```#{rank}```",
            inline=True
        )
        embed.add_field(
            name="Total XP",
            value=f"```{xp:,}```",
            inline=True
        )
        
        # Progress bar
        progress_bar = self.create_progress_bar(progress)
        embed.add_field(
            name=f"Progress to Level {level + 1}",
            value=f"{progress_bar} ({xp_progress:,}/{xp_needed:,} XP)",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    def create_progress_bar(self, percent: float, length: int = 20) -> str:
        filled = int(percent * length / 100)
        return f"[{'■' * filled}{'□' * (length - filled)}]"
        
    async def get_rank(self, user_id: int) -> int:
        async with self.bot.pool.acquire() as conn:
            rank = await conn.fetchval("""
                SELECT COUNT(*) + 1 FROM levels
                WHERE xp > (
                    SELECT xp FROM levels WHERE user_id = ?
                )
            """, (str(user_id),))
            return rank
            
    @commands.command(name="leaderboard", aliases=["lb"])
    async def show_leaderboard(self, ctx):
        """Tampilkan leaderboard level"""
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, xp
                FROM levels
                ORDER BY xp DESC
                LIMIT 10
            """)
            
        if not rows:
            return await ctx.send("❌ Belum ada data level!")
            
        embed = discord.Embed(
            title="🏆 Level Leaderboard",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        for idx, row in enumerate(rows, 1):
            user = self.bot.get_user(int(row['user_id']))
            if user:
                level = int((row['xp'] / 100) ** 0.5)
                embed.add_field(
                    name=f"#{idx} {user.name}",
                    value=f"Level {level} | {row['xp']:,} XP",
                    inline=False
                )
                
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Leveling(bot))