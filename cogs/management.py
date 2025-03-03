import discord
from discord.ext import commands
import logging
from datetime import datetime

class ServerManagement(commands.Cog):
    """🛠️ Server Management System"""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('Management')

    # Moderasi
    @commands.command(name='kick')
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """👢 Kick member dari server"""
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(
                title="Member Kicked",
                description=f"✅ {member.mention} telah dikick!",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            if reason:
                embed.add_field(name="Alasan", value=reason)
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak memiliki izin untuk kick member!")

    @commands.command(name='ban')
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = None):
        """🔨 Ban member dari server"""
        try:
            await member.ban(reason=reason)
            embed = discord.Embed(
                title="Member Banned",
                description=f"✅ {member.mention} telah dibanned!",
                color=discord.Color.dark_red(),
                timestamp=datetime.utcnow()
            )
            if reason:
                embed.add_field(name="Alasan", value=reason)
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak memiliki izin untuk ban member!")

    @commands.command(name='unban')
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, member_id: int):
        """🔓 Unban member dari server"""
        try:
            user = await self.bot.fetch_user(member_id)
            await ctx.guild.unban(user)
            embed = discord.Embed(
                title="Member Unbanned",
                description=f"✅ {user.mention} telah diunban!",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed)
        except discord.NotFound:
            await ctx.send("❌ User tidak ditemukan!")
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak memiliki izin untuk unban member!")

    # Channel Management
    @commands.command(name='createchannel')
    @commands.has_permissions(manage_channels=True)
    async def createchannel(self, ctx, channel_name: str, *, category: str = None):
        """📝 Buat channel baru"""
        try:
            if category:
                category_obj = discord.utils.get(ctx.guild.categories, name=category)
                channel = await ctx.guild.create_text_channel(channel_name, category=category_obj)
            else:
                channel = await ctx.guild.create_text_channel(channel_name)
            
            embed = discord.Embed(
                title="Channel Created",
                description=f"✅ Channel {channel.mention} telah dibuat!",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak memiliki izin untuk membuat channel!")

    @commands.command(name='deletechannel')
    @commands.has_permissions(manage_channels=True)
    async def deletechannel(self, ctx, channel: discord.TextChannel):
        """🗑️ Hapus channel"""
        try:
            channel_name = channel.name
            await channel.delete()
            embed = discord.Embed(
                title="Channel Deleted",
                description=f"✅ Channel #{channel_name} telah dihapus!",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak memiliki izin untuk menghapus channel!")

    # Role Management
    @commands.command(name='addrole')
    @commands.has_permissions(manage_roles=True)
    async def addrole(self, ctx, member: discord.Member, role: discord.Role):
        """➕ Tambah role ke member"""
        try:
            await member.add_roles(role)
            embed = discord.Embed(
                title="Role Added",
                description=f"✅ Role {role.mention} telah ditambahkan ke {member.mention}!",
                color=role.color,
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak memiliki izin untuk menambah role!")

    @commands.command(name='removerole')
    @commands.has_permissions(manage_roles=True)
    async def removerole(self, ctx, member: discord.Member, role: discord.Role):
        """➖ Hapus role dari member"""
        try:
            await member.remove_roles(role)
            embed = discord.Embed(
                title="Role Removed",
                description=f"✅ Role {role.mention} telah dihapus dari {member.mention}!",
                color=role.color,
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak memiliki izin untuk menghapus role!")

async def setup(bot):
    await bot.add_cog(ServerManagement(bot))