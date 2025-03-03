import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
import os
from datetime import datetime

class Welcome(commands.Cog):
    """👋 Sistem Welcome Advanced"""
    
    def __init__(self, bot):
        self.bot = bot
        self.font_path = "assets/fonts/"  # Pastikan folder dan font tersedia
        self.background_path = "assets/backgrounds/"
        
    async def create_welcome_card(self, member):
        """Buat kartu welcome dengan gambar"""
        # Load background
        background = Image.open(f"{self.background_path}welcome_bg.png")
        draw = ImageDraw.Draw(background)
        
        # Load fonts
        title_font = ImageFont.truetype(f"{self.font_path}title.ttf", 60)
        subtitle_font = ImageFont.truetype(f"{self.font_path}subtitle.ttf", 40)
        
        # Download dan pasang avatar
        async with aiohttp.ClientSession() as session:
            async with session.get(str(member.display_avatar.url)) as resp:
                avatar_bytes = await resp.read()
                
        # Proses avatar
        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
            avatar = avatar.resize((200, 200))
            mask = Image.new("L", avatar.size, 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, 200, 200), fill=255)
            
            # Paste avatar
            background.paste(avatar, (350, 50), mask)
            
        # Tambah text
        draw.text(
            (450, 280),
            f"Welcome {member.name}!",
            font=title_font,
            fill="white",
            anchor="ms"
        )
        draw.text(
            (450, 340),
            f"Member #{len(member.guild.members)}",
            font=subtitle_font,
            fill="lightgray",
            anchor="ms"
        )
        
        # Convert ke bytes
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        
        return buffer
        
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle member join dengan welcome card"""
        # Get welcome channel
        channel_id = self.bot.config['channels'].get('welcome')
        if not channel_id:
            return
            
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return
            
        # Create welcome card
        card_buffer = await self.create_welcome_card(member)
        
        # Create embed
        embed = discord.Embed(
            title="👋 Welcome to the Server!",
            description=f"Selamat datang {member.mention} di {member.guild.name}!",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        # Add member info
        embed.add_field(
            name="Account Created",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True
        )
        embed.add_field(
            name="Member Count",
            value=str(len(member.guild.members)),
            inline=True
        )
        
        # Add rules reminder
        embed.add_field(
            name="📜 Please Read",
            value="Jangan lupa baca rules di <#rules_channel_id>",
            inline=False
        )
        
        # Send welcome message
        file = discord.File(card_buffer, "welcome.png")
        embed.set_image(url="attachment://welcome.png")
        
        welcome_msg = await channel.send(
            content=member.mention,
            embed=embed,
            file=file
        )
        
        # Add reaction for role
        await welcome_msg.add_reaction("✅")
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reaction untuk auto-role"""
        if payload.member.bot:
            return
            
        channel_id = self.bot.config['channels'].get('welcome')
        if not channel_id or payload.channel_id != int(channel_id):
            return
            
        if str(payload.emoji) == "✅":
            # Get verified role
            role_id = self.bot.config['roles'].get('verified')
            if not role_id:
                return
                
            role = payload.member.guild.get_role(int(role_id))
            if role:
                await payload.member.add_roles(role)
                
    @commands.group(name="welcome")
    @commands.has_permissions(administrator=True)
    async def welcome(self, ctx):
        """⚙️ Pengaturan welcome system"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
            
    @welcome.command(name="test")
    async def test_welcome(self, ctx):
        """Test welcome message"""
        card_buffer = await self.create_welcome_card(ctx.author)
        
        embed = discord.Embed(
            title="👋 Welcome Message Test",
            description=f"This is how the welcome message will look for new members.",
            color=discord.Color.blue()
        )
        
        file = discord.File(card_buffer, "welcome_test.png")
        embed.set_image(url="attachment://welcome_test.png")
        
        await ctx.send(embed=embed, file=file)
        
    @welcome.command(name="setchannel")
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        """Set welcome channel"""
        self.bot.config['channels']['welcome'] = channel.id
        await self.bot.save_config()
        await ctx.send(f"✅ Welcome channel set to {channel.mention}")
        
    @welcome.command(name="setrole")
    async def set_verified_role(self, ctx, role: discord.Role):
        """Set verified role"""
        self.bot.config['roles']['verified'] = role.id
        await self.bot.save_config()
        await ctx.send(f"✅ Verified role set to {role.mention}")

async def setup(bot):
    await bot.add_cog(Welcome(bot))