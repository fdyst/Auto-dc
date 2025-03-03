import discord
from discord.ext import commands
import asyncio
import datetime
import re
from typing import Optional

class Reminders(commands.Cog):
    """⏰ Sistem Pengingat"""
    
    def __init__(self, bot):
        self.bot = bot
        self.reminders = {}
        self.load_reminders.start()
        
    def cog_unload(self):
        self.load_reminders.cancel()
        
    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Check for due reminders"""
        current_time = datetime.datetime.utcnow()
        
        for user_id, user_reminders in list(self.reminders.items()):
            for reminder in user_reminders[:]:
                if current_time >= reminder['time']:
                    user = self.bot.get_user(int(user_id))
                    if user:
                        embed = discord.Embed(
                            title="⏰ Reminder!",
                            description=reminder['text'],
                            color=discord.Color.blue(),
                            timestamp=current_time
                        )
                        try:
                            await user.send(embed=embed)
                        except discord.Forbidden:
                            pass
                            
                    user_reminders.remove(reminder)
                    if not user_reminders:
                        del self.reminders[user_id]
                        
                    # Remove from database
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute("""
                            DELETE FROM reminders
                            WHERE user_id = ? AND reminder_time = ?
                        """, (user_id, reminder['time']))
                        
    def parse_time(self, time_str: str) -> Optional[datetime.timedelta]:
        """Parse time string into timedelta"""
        time_units = {
            's': 'seconds',
            'm': 'minutes',
            'h': 'hours',
            'd': 'days',
            'w': 'weeks'
        }
        
        pattern = r'(\d+)([smhdw])'
        matches = re.findall(pattern, time_str.lower())
        
        if not matches:
            return None
            
        td_args = {}
        for value, unit in matches:
            td_args[time_units[unit]] = int(value)
            
        return datetime.timedelta(**td_args)
        
    @commands.command(name="remind")
    async def set_reminder(self, ctx, time: str, *, reminder: str):
        """⏰ Set pengingat baru
        Contoh: !remind 1h30m Makan siang"""
        
        delta = self.parse_time(time)
        if not delta:
            return await ctx.send("❌ Format waktu tidak valid! Contoh: 1h30m")
            
        reminder_time = datetime.datetime.utcnow() + delta
        
        if str(ctx.author.id) not in self.reminders:
            self.reminders[str(ctx.author.id)] = []
            
        self.reminders[str(ctx.author.id)].append({
            'text': reminder,
            'time': reminder_time
        })
        
        # Save to database
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO reminders (user_id, reminder_text, reminder_time)
                VALUES (?, ?, ?)
            """, (str(ctx.author.id), reminder, reminder_time))
            
        embed = discord.Embed(
            title="⏰ Reminder Set!",
            description=f"I'll remind you about: {reminder}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(
            name="When",
            value=f"<t:{int(reminder_time.timestamp())}:R>"
        )
        
        await ctx.send(embed=embed)
        
    @commands.command(name="reminders")
    async def list_reminders(self, ctx):
        """📋 Lihat daftar pengingat"""
        if str(ctx.author.id) not in self.reminders or not self.reminders[str(ctx.author.id)]:
            return await ctx.send("❌ Anda tidak memiliki pengingat aktif!")
            
        embed = discord.Embed(
            title="📋 Your Reminders",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        for idx, reminder in enumerate(self.reminders[str(ctx.author.id)], 1):
            embed.add_field(
                name=f"Reminder #{idx}",
                value=f"**Text:** {reminder['text']}\n"
                      f"**When:** <t:{int(reminder['time'].timestamp())}:R>",
                inline=False
            )
            
        await ctx.send(embed=embed)
        
    @commands.command(name="delreminder")
    async def delete_reminder(self, ctx, index: int):
        """🗑️ Hapus pengingat"""
        if (str(ctx.author.id) not in self.reminders or 
            not self.reminders[str(ctx.author.id)] or 
            index > len(self.reminders[str(ctx.author.id)])):
            return await ctx.send("❌ Pengingat tidak ditemukan!")
            
        reminder = self.reminders[str(ctx.author.id)].pop(index - 1)
        if not self.reminders[str(ctx.author.id)]:
            del self.reminders[str(ctx.author.id)]
            
        # Remove from database
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM reminders
                WHERE user_id = ? AND reminder_time = ?
            """, (str(ctx.author.id), reminder['time']))
            
        embed = discord.Embed(
            title="🗑️ Reminder Deleted",
            description=f"Deleted reminder: {reminder['text']}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @tasks.loop(minutes=1)
    async def load_reminders(self):
        """Load reminders from database"""
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM reminders
                WHERE reminder_time > datetime('now')
            """)
            
        for row in rows:
            user_id = str(row['user_id'])
            if user_id not in self.reminders:
                self.reminders[user_id] = []
                
            self.reminders[user_id].append({
                'text': row['reminder_text'],
                'time': row['reminder_time']
            })

async def setup(bot):
    await bot.add_cog(Reminders(bot))