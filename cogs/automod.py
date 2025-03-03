import discord
from discord.ext import commands
import re
from datetime import datetime, timedelta
import json

class AutoMod(commands.Cog):
    """🛡️ Sistem Moderasi Otomatis"""
    
    def __init__(self, bot):
        self.bot = bot
        self.spam_check = {}
        self.config = self.load_config()
        
    def load_config(self):
        try:
            with open('config/automod.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            default = {
                "enabled": True,
                "spam_threshold": 5,
                "caps_threshold": 0.7,
                "banned_words": [],
                "warn_threshold": 3,
                "mute_duration": 10  # minutes
            }
            with open('config/automod.json', 'w') as f:
                json.dump(default, f, indent=4)
            return default
            
    @commands.Cog.listener()
    async def on_message(self, message):
        if not self.config["enabled"] or message.author.bot:
            return
            
        if await self.check_spam(message):
            await self.handle_violation(message, "spam")
            
        if await self.check_caps(message):
            await self.handle_violation(message, "caps")
            
        if await self.check_banned_words(message):
            await self.handle_violation(message, "banned_words")
            
    async def check_spam(self, message):
        author_id = str(message.author.id)
        current_time = datetime.utcnow()
        
        if author_id not in self.spam_check:
            self.spam_check[author_id] = []
            
        self.spam_check[author_id].append(current_time)
        self.spam_check[author_id] = [
            msg_time for msg_time in self.spam_check[author_id]
            if current_time - msg_time < timedelta(seconds=5)
        ]
        
        return len(self.spam_check[author_id]) >= self.config["spam_threshold"]
        
    async def check_caps(self, message):
        if len(message.content) < 10:
            return False
            
        caps_count = sum(1 for c in message.content if c.isupper())
        caps_ratio = caps_count / len(message.content)
        
        return caps_ratio > self.config["caps_threshold"]
        
    async def check_banned_words(self, message):
        return any(word.lower() in message.content.lower() 
                  for word in self.config["banned_words"])
                  
    async def handle_violation(self, message, violation_type):
        embed = discord.Embed(
            title="⚠️ AutoMod Violation",
            description=f"Pelanggaran terdeteksi di {message.channel.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User", value=message.author.mention)
        embed.add_field(name="Type", value=violation_type.title())
        
        try:
            await message.delete()
            await message.channel.send(embed=embed, delete_after=5)
            
            # Add warning to database
            await self.add_warning(message.author.id, violation_type)
            
            # Check warning threshold
            warnings = await self.get_warnings(message.author.id)
            if len(warnings) >= self.config["warn_threshold"]:
                await self.mute_user(message.author)
                
        except discord.Forbidden:
            pass
            
    async def mute_user(self, member):
        muted_role = discord.utils.get(member.guild.roles, name="Muted")
        if not muted_role:
            muted_role = await member.guild.create_role(name="Muted")
            
        await member.add_roles(muted_role)
        await asyncio.sleep(self.config["mute_duration"] * 60)
        await member.remove_roles(muted_role)
        
    @commands.group(name="automod")
    @commands.has_permissions(administrator=True)
    async def automod(self, ctx):
        """Pengaturan AutoMod"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
            
    @automod.command(name="toggle")
    async def toggle_automod(self, ctx, state: bool):
        """Toggle AutoMod on/off"""
        self.config["enabled"] = state
        self.save_config()
        await ctx.send(f"✅ AutoMod has been {'enabled' if state else 'disabled'}")
        
    @automod.command(name="addword")
    async def add_banned_word(self, ctx, word: str):
        """Tambah kata yang dilarang"""
        self.config["banned_words"].append(word.lower())
        self.save_config()
        await ctx.send(f"✅ Added '{word}' to banned words")
        
    @automod.command(name="removeword")
    async def remove_banned_word(self, ctx, word: str):
        """Hapus kata dari daftar larangan"""
        try:
            self.config["banned_words"].remove(word.lower())
            self.save_config()
            await ctx.send(f"✅ Removed '{word}' from banned words")
        except ValueError:
            await ctx.send("❌ Word not found in banned words list")
            
    def save_config(self):
        with open('config/automod.json', 'w') as f:
            json.dump(self.config, f, indent=4)

async def setup(bot):
    await bot.add_cog(AutoMod(bot))