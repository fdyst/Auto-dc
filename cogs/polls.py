import discord
from discord.ext import commands
from typing import List

class Polls(commands.Cog):
    """📊 Sistem Polling"""
    
    def __init__(self, bot):
        self.bot = bot
        self.emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", 
                            "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                            
    @commands.command(name="poll")
    async def create_poll(self, ctx, question: str, *options: str):
        """Buat polling baru"""
        if len(options) < 2:
            return await ctx.send("❌ Berikan minimal 2 opsi!")
            
        if len(options) > 10:
            return await ctx.send("❌ Maksimal 10 opsi!")
            
        # Create embed
        embed = discord.Embed(
            title="📊 Poll",
            description=question,
            color=discord.Color.blue()
        )
        
        # Add options
        for idx, option in enumerate(options):
            embed.add_field(
                name=f"Option {idx + 1}",
                value=f"{self.emoji_numbers[idx]} {option}",
                inline=False
            )
            
        poll_msg = await ctx.send(embed=embed)
        
        # Add reactions
        for idx in range(len(options)):
            await poll_msg.add_reaction(self.emoji_numbers[idx])
            
    @commands.command(name="quickpoll")
    async def quick_poll(self, ctx, *, question: str):
        """Buat polling cepat (Yes/No)"""
        embed = discord.Embed(
            title="📊 Quick Poll",
            description=question,
            color=discord.Color.blue()
        )
        
        poll_msg = await ctx.send(embed=embed)
        await poll_msg.add_reaction("👍")
        await poll_msg.add_reaction("👎")

async def setup(bot):
    await bot.add_cog(Polls(bot))