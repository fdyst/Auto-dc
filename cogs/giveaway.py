import discord
from discord.ext import commands
import asyncio
from datetime import datetime
import random

class Giveaway(commands.Cog):
    """🎉 Sistem Giveaway"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_giveaways = {}
        
    @commands.command(name="gstart")
    @commands.has_permissions(manage_guild=True)
    async def start_giveaway(self, ctx, duration: str, winners: int, *, prize: str):
        """Mulai giveaway baru"""
        # Convert duration (1h, 1d, etc) to seconds
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        duration_seconds = int(duration[:-1]) * time_units[duration[-1].lower()]
        
        end_time = datetime.utcnow().timestamp() + duration_seconds
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=f"**Prize:** {prize}\n"
                      f"**Winners:** {winners}\n"
                      f"**Ends:** <t:{int(end_time)}:R>\n\n"
                      "React with 🎉 to enter!",
            color=discord.Color.blue()
        )
        
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")
        
        self.active_giveaways[msg.id] = {
            "end_time": end_time,
            "winners": winners,
            "prize": prize,
            "channel_id": ctx.channel.id,
            "message_id": msg.id,
            "host": ctx.author.id
        }
        
        await self.wait_for_giveaway(msg.id)
        
    async def wait_for_giveaway(self, message_id):
        """Wait for giveaway to end"""
        giveaway = self.active_giveaways[message_id]
        await asyncio.sleep(giveaway["end_time"] - datetime.utcnow().timestamp())
        
        channel = self.bot.get_channel(giveaway["channel_id"])
        message = await channel.fetch_message(message_id)
        
        # Get participants
        reaction = discord.utils.get(message.reactions, emoji="🎉")
        users = [user async for user in reaction.users() if not user.bot]
        
        if len(users) < giveaway["winners"]:
            winners = users
        else:
            winners = random.sample(users, giveaway["winners"])
            
        # Announce winners
        winners_text = ", ".join(w.mention for w in winners) if winners else "No valid participants"
        
        embed = discord.Embed(
            title="🎉 Giveaway Ended! 🎉",
            description=f"**Prize:** {giveaway['prize']}\n"
                      f"**Winners:** {winners_text}",
            color=discord.Color.green()
        )
        
        await message.edit(embed=embed)
        await channel.send(f"🎉 Congratulations {winners_text}! You won **{giveaway['prize']}**!")
        
        del self.active_giveaways[message_id]
        
    @commands.command(name="gend")
    @commands.has_permissions(manage_guild=True)
    async def end_giveaway(self, ctx, message_id: int):
        """End giveaway early"""
        if message_id in self.active_giveaways:
            self.active_giveaways[message_id]["end_time"] = datetime.utcnow().timestamp()
            await ctx.send("✅ Giveaway will end shortly!")
        else:
            await ctx.send("❌ Giveaway not found!")

    @commands.command(name="greroll")
    @commands.has_permissions(manage_guild=True)
    async def reroll_giveaway(self, ctx, message_id: int):
        """Reroll giveaway winners"""
        try:
            message = await ctx.channel.fetch_message(message_id)
            reaction = discord.utils.get(message.reactions, emoji="🎉")
            users = [user async for user in reaction.users() if not user.bot]
            
            if not users:
                return await ctx.send("❌ No valid participants found!")
                
            winner = random.choice(users)
            await ctx.send(f"🎉 New winner: {winner.mention}!")
            
        except discord.NotFound:
            await ctx.send("❌ Message not found!")

async def setup(bot):
    await bot.add_cog(Giveaway(bot))