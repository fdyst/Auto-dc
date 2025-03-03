import discord
from discord.ext import commands
import datetime
from collections import Counter
import matplotlib.pyplot as plt
import io
import pandas as pd

class ServerStats(commands.Cog):
    """📊 Sistem Statistik Server"""
    
    def __init__(self, bot):
        self.bot = bot
        self.message_history = {}
        self.voice_time = {}
        
    async def log_activity(self, guild_id: int, user_id: int, activity_type: str, timestamp: datetime.datetime):
        """Log aktivitas untuk statistik"""
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO activity_logs 
                (guild_id, user_id, activity_type, timestamp)
                VALUES (?, ?, ?, ?)
            """, (str(guild_id), str(user_id), activity_type, timestamp))

    @commands.command(name="serverstats")
    async def show_server_stats(self, ctx):
        """📊 Tampilkan statistik server"""
        guild = ctx.guild
        
        # Buat embed
        embed = discord.Embed(
            title=f"📊 Statistik Server {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        
        # Statistik dasar
        embed.add_field(
            name="👥 Member Stats",
            value=f"Total: {guild.member_count}\n"
                  f"Humans: {len([m for m in guild.members if not m.bot])}\n"
                  f"Bots: {len([m for m in guild.members if m.bot])}",
            inline=True
        )
        
        # Channel stats
        channels = Counter(c.type for c in guild.channels)
        embed.add_field(
            name="📺 Channel Stats",
            value=f"Text: {channels[discord.ChannelType.text]}\n"
                  f"Voice: {channels[discord.ChannelType.voice]}\n"
                  f"Categories: {len(guild.categories)}",
            inline=True
        )
        
        # Role stats
        embed.add_field(
            name="👑 Role Stats",
            value=f"Total Roles: {len(guild.roles)}\n"
                  f"Highest Role: {guild.roles[-1].name}",
            inline=True
        )
        
        # Server info
        embed.add_field(
            name="ℹ️ Server Info",
            value=f"Created: <t:{int(guild.created_at.timestamp())}:R>\n"
                  f"Owner: {guild.owner.mention}\n"
                  f"Region: {guild.preferred_locale}",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    @commands.command(name="rolestat")
    async def role_statistics(self, ctx):
        """📊 Tampilkan statistik role"""
        # Create role distribution chart
        roles = [role for role in ctx.guild.roles if not role.is_default()]
        member_counts = [len(role.members) for role in roles]
        role_names = [role.name for role in roles]
        
        plt.figure(figsize=(10, 6))
        plt.bar(role_names, member_counts)
        plt.xticks(rotation=45, ha='right')
        plt.title('Role Distribution')
        plt.tight_layout()
        
        # Save plot to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        # Send chart
        file = discord.File(buf, 'role_stats.png')
        await ctx.send(file=file)
        
    @commands.command(name="activitystats")
    async def activity_statistics(self, ctx, days: int = 7):
        """📈 Tampilkan statistik aktivitas"""
        async with self.bot.pool.acquire() as conn:
            data = await conn.fetch("""
                SELECT activity_type, COUNT(*) as count, 
                       strftime('%Y-%m-%d', timestamp) as date
                FROM activity_logs
                WHERE guild_id = ?
                AND timestamp > datetime('now', ?)
                GROUP BY activity_type, date
                ORDER BY date
            """, (str(ctx.guild.id), f'-{days} days'))
            
        if not data:
            return await ctx.send("❌ Tidak ada data aktivitas!")
            
        # Create activity chart
        df = pd.DataFrame(data)
        pivot = df.pivot(index='date', columns='activity_type', values='count')
        
        plt.figure(figsize=(10, 6))
        pivot.plot(kind='line', marker='o')
        plt.title(f'Server Activity (Last {days} days)')
        plt.xlabel('Date')
        plt.ylabel('Activity Count')
        plt.legend(title='Activity Type')
        plt.tight_layout()
        
        # Save plot to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        # Send chart
        file = discord.File(buf, 'activity_stats.png')
        await ctx.send(file=file)
        
    @commands.command(name="memberhistory")
    async def member_history(self, ctx):
        """📈 Tampilkan history member"""
        async with self.bot.pool.acquire() as conn:
            data = await conn.fetch("""
                SELECT COUNT(*) as count,
                       strftime('%Y-%m-%d', joined_at) as date
                FROM member_history
                WHERE guild_id = ?
                GROUP BY date
                ORDER BY date
            """, (str(ctx.guild.id),))
            
        if not data:
            return await ctx.send("❌ Tidak ada data history member!")
            
        # Create member history chart
        dates = [row['date'] for row in data]
        counts = [row['count'] for row in data]
        
        plt.figure(figsize=(10, 6))
        plt.plot(dates, counts, marker='o')
        plt.title('Member Growth History')
        plt.xlabel('Date')
        plt.ylabel('Member Count')
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save plot to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        # Send chart
        file = discord.File(buf, 'member_history.png')
        await ctx.send(file=file)
        
    @commands.Cog.listener()
    async def on_message(self, message):
        """Log message activity"""
        if not message.guild or message.author.bot:
            return
            
        await self.log_activity(
            message.guild.id,
            message.author.id,
            'message',
            message.created_at
        )
        
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Log voice activity"""
        if not member.guild:
            return
            
        if before.channel is None and after.channel is not None:
            # Member joined voice
            await self.log_activity(
                member.guild.id,
                member.id,
                'voice_join',
                datetime.datetime.utcnow()
            )
            
        elif before.channel is not None and after.channel is None:
            # Member left voice
            await self.log_activity(
                member.guild.id,
                member.id,
                'voice_leave',
                datetime.datetime.utcnow()
            )

async def setup(bot):
    await bot.add_cog(ServerStats(bot))