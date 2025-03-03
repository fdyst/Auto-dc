import discord
from discord.ext import commands
import youtube_dl
import asyncio
from async_timeout import timeout
from functools import partial
import itertools

# Youtube-dl options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]
            
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class Music(commands.Cog):
    """🎵 Sistem Musik"""
    
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self._current_player = {}
        
    def get_queue(self, guild_id):
        """Get guild queue"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]
        
    @commands.command(name="join")
    async def join(self, ctx):
        """➡️ Join voice channel"""
        if ctx.author.voice is None:
            return await ctx.send("❌ Anda harus berada di voice channel!")
            
        channel = ctx.author.voice.channel
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
            
    @commands.command(name="play")
    async def play(self, ctx, *, query):
        """🎵 Play music"""
        if ctx.author.voice is None:
            return await ctx.send("❌ Anda harus berada di voice channel!")
            
        if ctx.voice_client is None:
            await ctx.invoke(self.join)
            
        async with ctx.typing():
            try:
                player = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True)
                if not ctx.voice_client.is_playing():
                    ctx.voice_client.play(player)
                    self._current_player[ctx.guild.id] = player
                    await ctx.send(f"🎵 Now playing: **{player.title}**")
                else:
                    self.get_queue(ctx.guild.id).append(player)
                    await ctx.send(f"🎵 Added to queue: **{player.title}**")
            except Exception as e:
                await ctx.send(f"❌ Error: {str(e)}")
                
    @commands.command(name="pause")
    async def pause(self, ctx):
        """⏸️ Pause music"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Music paused")
        else:
            await ctx.send("❌ Nothing is playing!")
            
    @commands.command(name="resume")
    async def resume(self, ctx):
        """▶️ Resume music"""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Music resumed")
        else:
            await ctx.send("❌ Nothing is paused!")
            
    @commands.command(name="stop")
    async def stop(self, ctx):
        """⏹️ Stop music"""
        if ctx.voice_client:
            ctx.voice_client.stop()
            self.queues[ctx.guild.id] = []
            await ctx.send("⏹️ Music stopped")
        else:
            await ctx.send("❌ Not connected to voice!")
            
    @commands.command(name="skip")
    async def skip(self, ctx):
        """⏭️ Skip current song"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ Skipped song")
            
            # Play next in queue
            queue = self.get_queue(ctx.guild.id)
            if queue:
                next_player = queue.pop(0)
                ctx.voice_client.play(next_player)
                self._current_player[ctx.guild.id] = next_player
                await ctx.send(f"🎵 Now playing: **{next_player.title}**")
        else:
            await ctx.send("❌ Nothing is playing!")
            
    @commands.command(name="queue", aliases=["q"])
    async def show_queue(self, ctx):
        """📋 Show music queue"""
        queue = self.get_queue(ctx.guild.id)
        if not queue and not ctx.voice_client.is_playing():
            return await ctx.send("❌ Queue is empty!")
            
        embed = discord.Embed(
            title="🎵 Music Queue",
            color=discord.Color.blue()
        )
        
        if ctx.voice_client.is_playing():
            current = self._current_player[ctx.guild.id]
            embed.add_field(
                name="Now Playing",
                value=f"**{current.title}**",
                inline=False
            )
            
        if queue:
            queue_list = "\n".join(
                f"{idx+1}. {player.title}"
                for idx, player in enumerate(queue[:10])
            )
            if len(queue) > 10:
                queue_list += f"\n... and {len(queue)-10} more"
                
            embed.add_field(
                name="Up Next",
                value=queue_list,
                inline=False
            )
            
        await ctx.send(embed=embed)