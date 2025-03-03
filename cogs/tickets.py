import discord
from discord.ext import commands
import asyncio
from datetime import datetime

class TicketSystem(commands.Cog):
    """🎫 Sistem Ticket Support"""
    
    def __init__(self, bot):
        self.bot = bot
        self.ticket_category = None
        
    async def get_ticket_category(self, guild):
        """Get or create ticket category"""
        if not self.ticket_category:
            self.ticket_category = discord.utils.get(guild.categories, name="Tickets")
            if not self.ticket_category:
                self.ticket_category = await guild.create_category("Tickets")
        return self.ticket_category
        
    @commands.command(name="ticket")
    async def create_ticket(self, ctx, *, reason: str = "No reason provided"):
        """Buat ticket support baru"""
        category = await self.get_ticket_category(ctx.guild)
        
        # Create ticket channel
        channel_name = f"ticket-{ctx.author.name}-{len(category.channels) + 1}"
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        
        channel = await ctx.guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites
        )
        
        embed = discord.Embed(
            title="🎫 Ticket Support",
            description=f"Ticket dibuat oleh {ctx.author.mention}\n"
                      f"**Reason:** {reason}\n\n"
                      "Staff akan segera membantu Anda.\n"
                      "Gunakan `!close` untuk menutup ticket.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        await channel.send(embed=embed)
        await ctx.send(f"✅ Ticket dibuat di {channel.mention}")
        
    @commands.command(name="close")
    async def close_ticket(self, ctx):
        """Tutup ticket"""
        if not ctx.channel.category or ctx.channel.category.name != "Tickets":
            return await ctx.send("❌ Command ini hanya bisa digunakan di channel ticket!")
            
        await ctx.send("🔒 Ticket akan ditutup dalam 5 detik...")
        await asyncio.sleep(5)
        await ctx.channel.delete()
        
    @commands.command(name="adduser")
    @commands.has_permissions(manage_channels=True)
    async def add_to_ticket(self, ctx, member: discord.Member):
        """Tambah user ke ticket"""
        if not ctx.channel.category or ctx.channel.category.name != "Tickets":
            return await ctx.send("❌ Command ini hanya bisa digunakan di channel ticket!")
            
        await ctx.channel.set_permissions(member, read_messages=True)
        await ctx.send(f"✅ {member.mention} ditambahkan ke ticket")

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))