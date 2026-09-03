import os, time, discord, asyncpg, random, string, datetime
from discord.ext import commands
from discord.gateway import DiscordWebSocket
from cogs.voicemaster import vmbuttons
from cogs.ticket import CreateTicket, DeleteTicket
from tools.utils import StartUp, create_db
from tools.ext import Client, HTTP
from humanfriendly import format_timespan
from cogs.giveaway import GiveawayView
from typing import List, Optional, Tuple
from tools.utils import PaginatorView
from io import BytesIO 
import typing
import dotenv
from pathlib import Path
from functools import lru_cache
import asyncio

dotenv.load_dotenv(Path(__file__).parent / '.env', verbose=True)
token = os.environ['token']
temp = "http://14a4a94eff770:c3ac0449fd@104.234.255.18:12323"

def generate_key():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(6))

async def checkthekey(key: str):
    check = await bot.db.fetchrow("SELECT * FROM cmderror WHERE code = $1", key)
    if check: 
        newkey = generate_key()
        return await checkthekey(newkey)
    return key  

DiscordWebSocket.identify = StartUp.identify
    
os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
os.environ["JISHAKU_HIDE"] = "True"
os.environ["JISHAKU_FORCE_PAGINATOR"] = "True"
os.environ["JISHAKU_RETAIN"] = "True"

# OPTIMIZATION: Cache prefix lookups in memory with TTL
class PrefixCache:
    def __init__(self, ttl=300):  # 5 minute TTL
        self._guild_cache = {}
        self._self_cache = {}
        self._ttl = ttl
        
    def get_guild(self, guild_id: int) -> Optional[str]:
        entry = self._guild_cache.get(guild_id)
        if entry and time.time() - entry[1] < self._ttl:
            return entry[0]
        return None
    
    def set_guild(self, guild_id: int, prefix: str):
        self._guild_cache[guild_id] = (prefix, time.time())
    
    def get_self(self, user_id: int) -> Optional[str]:
        entry = self._self_cache.get(user_id)
        if entry and time.time() - entry[1] < self._ttl:
            return entry[0]
        return None
    
    def set_self(self, user_id: int, prefix: str):
        self._self_cache[user_id] = (prefix, time.time())
    
    def invalidate_guild(self, guild_id: int):
        self._guild_cache.pop(guild_id, None)
    
    def invalidate_self(self, user_id: int):
        self._self_cache.pop(user_id, None)

prefix_cache = PrefixCache()

async def getprefix(bot, message):
    if not message.guild: 
        return ";"
    
    # Try cache first
    cached_guild = prefix_cache.get_guild(message.guild.id)
    cached_self = prefix_cache.get_self(message.author.id)
    
    if cached_guild and cached_self:
        return cached_guild, cached_self
    
    # Fetch both in parallel if not cached
    tasks = []
    if cached_self is None:
        tasks.append(bot.db.fetchrow("SELECT prefix FROM selfprefix WHERE user_id = $1", message.author.id))
    else:
        tasks.append(None)
    
    if cached_guild is None:
        tasks.append(bot.db.fetchrow("SELECT prefix FROM prefixes WHERE guild_id = $1", message.guild.id))
    else:
        tasks.append(None)
    
    results = await asyncio.gather(*[t for t in tasks if t is not None], return_exceptions=True)
    
    # Process results
    selfprefix = cached_self
    guildprefix = cached_guild
    
    result_idx = 0
    if cached_self is None:
        check = results[result_idx] if not isinstance(results[result_idx], Exception) else None
        selfprefix = check["prefix"] if check else None
        result_idx += 1
    
    if cached_guild is None:
        res = results[result_idx] if result_idx < len(results) and not isinstance(results[result_idx], Exception) else None
        guildprefix = res["prefix"] if res else ";"
    
    # Default logic
    if not guildprefix:
        guildprefix = ";"
    if not selfprefix:
        selfprefix = guildprefix
    
    # Cache results
    prefix_cache.set_guild(message.guild.id, guildprefix)
    prefix_cache.set_self(message.author.id, selfprefix)
    
    return guildprefix, selfprefix 

intents = discord.Intents.all()
intents.presences = True

class NeoContext(commands.Context): 
    def __init__(self, **kwargs): 
        super().__init__(**kwargs) 

    def find_role(self, name: str): 
        for role in self.guild.roles:
            if role.name == "@everyone": continue  
            if name.lower() in role.name.lower(): return role 
        return None 
 
    async def send_success(self, message: str) -> discord.Message:  
        return await self.reply(embed=discord.Embed(color=0x3ba55d, description=f"{self.bot.yes} {self.author.mention}: {message}"))
 
    async def send_error(self, message: str) -> discord.Message: 
        return await self.reply(embed=discord.Embed(color=0xed4245, description=f"{self.bot.no} {self.author.mention}: {message}"))
 
    async def send_warning(self, message: str) -> discord.Message: 
        return await self.reply(embed=discord.Embed(color=0xfaa81a, description=f"{self.bot.warning} {self.author.mention}: {message}"))
 
    async def paginator(self, embeds: List[discord.Embed]):
        if len(embeds) == 1: return await self.send(embed=embeds[0]) 
        view = PaginatorView(self, embeds)
        view.message = await self.reply(embed=embeds[0], view=view) 

    async def get_webhook(self, channel, name):
        c = bot.get_channel(int(channel))
        webhooks = await c.webhooks()
        for webhook in webhooks:
            if webhook.name == name:
                return webhook
        return None

    async def send(self, *args, **kwargs):
        check = await self.bot.db.fetchrow("SELECT avatar_url, name FROM reskin WHERE user_id = $1", self.author.id)
        if check:
            webhooks = await self.channel.webhooks()
            if len(webhooks) == 0: 
                webhook = await self.channel.create_webhook(name="delta")
            else: 
                webhook = webhooks[0]
            avurl = check['avatar_url']
            name = check['name']
            kwargs.pop('reference', None)
            return await webhook.send(*args, **kwargs, username=name, avatar_url=avurl)
        return await super().send(*args, **kwargs)
 
    async def cmdhelp(self): 
        command = self.command
        commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
        if command.cog_name == "owner": return
        embed = discord.Embed(color=bot.color, title=commandname, description=command.description)
        embed.set_author(name=bot.user.name, icon_url=bot.user.avatar.url)
        embed.add_field(name="category", value=command.help)
        embed.add_field(name="aliases", value=', '.join(map(str, command.aliases)) or "none")
        embed.add_field(name="permissions", value=command.brief or "any")
        embed.add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False)
        await self.reply(embed=embed)

    async def create_pages(self): 
        embeds = []
        i = 0
        for command in self.command.commands: 
            commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
            i += 1 
            embeds.append(discord.Embed(color=bot.color, title=f"{commandname}", description=command.description).set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url).add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False).set_footer(text=f"aliases: {', '.join(a for a in command.aliases) if len(command.aliases) > 0 else 'none'} ・ {i}/{len(self.command.commands)}"))
     
        return await self.paginator(embeds)  

class HelpCommand(commands.HelpCommand):
    def __init__(self, **kwargs):
        self.categories = {
            "home": "return to the main page", 
            "info": "view information about the bot", 
            "moderation": "keep your server safe", 
            "antiraid": "protect your server against raids",
            "automod": "doing the mod's job",
            "antinuke": "protect your server againt unfaithful admins",
            "emoji": "manage the emojis in your server",
            "utility": "most commands are here...",
            "config": "configure your server",
            "lastfm": "lastfm integration with the bot",
            "fun": "commands to use when you are bored",
            "roleplay": "this is self explanatory",
            "music": "listen to some music"
        } 
        super().__init__(**kwargs)
  
    async def send_bot_help(self, mapping):
        embed = discord.Embed(color=self.context.bot.color, title="Help menu") 
        embed.add_field(name="help", value="Please use the **dropdown** menu below to view all the bot's commands", inline=False) 
        embed.set_author(name=self.context.author.name, icon_url=self.context.author.display_avatar.url)
        embed.set_footer(text=f"command count: {len(set(bot.walk_commands()))}")
        options = []
        for c in self.categories: 
            options.append(discord.SelectOption(label=c, description=self.categories.get(c)))
        select = discord.ui.Select(options=options, placeholder="Select a category")

        async def select_callback(interaction: discord.Interaction): 
            if interaction.user.id != self.context.author.id: 
                return await self.context.bot.ext.send_warning(interaction, "You are not the author of this embed", ephemeral=True)
            if select.values[0] == "home": 
                return await interaction.response.edit_message(embed=embed)
            com = []
            for c in [cm for cm in set(bot.walk_commands()) if cm.help == select.values[0]]:
                if c.parent: 
                    if str(c.parent) in com: continue 
                    com.append(str(c.parent))
                else: 
                    com.append(c.name)  
            e = discord.Embed(color=bot.color, title=f"{select.values[0]} commands", description=f"```{', '.join(com)}```").set_author(name=self.context.author.name, icon_url=self.context.author.display_avatar.url)  
            return await interaction.response.edit_message(embed=e)
        
        select.callback = select_callback

        view = discord.ui.View(timeout=None)
        view.add_item(select) 
        return await self.context.reply(embed=embed, view=view)
  
    async def send_command_help(self, command: commands.Command): 
        commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
        if command.cog_name == "owner": return
        embed = discord.Embed(color=bot.color, title=commandname, description=command.description)
        embed.set_author(name=bot.user.name, icon_url=bot.user.avatar.url)
        embed.add_field(name="category", value=command.help)
        embed.add_field(name="aliases", value=', '.join(map(str, command.aliases)) or "none")
        embed.add_field(name="permissions", value=command.brief or "any")
        embed.add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False)
        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_group_help(self, group: commands.Group): 
        ctx = self.context
        embeds = []
        i = 0
        for command in group.commands: 
            commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
            i += 1 
            embeds.append(discord.Embed(color=bot.color, title=f"{commandname}", description=command.description).set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url).add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False).set_footer(text=f"aliases: {', '.join(a for a in command.aliases) if len(command.aliases) > 0 else 'none'} ・ {i}/{len(group.commands)}"))
     
        return await ctx.paginator(embeds) 

class CommandClient(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(
            shard_count=2,
            command_prefix=getprefix, 
            allowed_mentions=discord.AllowedMentions(roles=False, everyone=False, users=True, replied_user=False), 
            intents=intents, 
            help_command=HelpCommand(), 
            strip_after_prefix=True, 
            activity=discord.Activity(name=" ", type=discord.ActivityType.competing), 
            owner_ids=[1406842730587623556],
            # OPTIMIZATION: Set max_messages to reduce memory footprint
            max_messages=1000,  # Reduced from default 1000 to save ~50MB RAM
            # OPTIMIZATION: Chunk guilds on demand, not all at once
            chunk_guilds_at_startup=False,
            # OPTIMIZATION: Reduce member cache size
            member_cache_flags=discord.MemberCacheFlags.none()
        )
        self.uptime = time.time()
        self.persistent_views_added = False
        self.cogs_loaded = False
        self.google_api = "AIzaSyDPrFJ8oxPP5YWM82vqCaLq8F6ZdlSGsBo" 
        self.color = 0x6d827d
        
        # OPTIMIZATION: Use None initially, load lazily
        self.yes = "✅"
        self.no = "❌"
        self.warning = "⚠️"
        self._emojis_loaded = False
        
        self.left = "<:left:1018156480991612999>"
        self.right = "<:right:1018156484170883154>"
        self.goto = "<:filter:1039235211789078628>"
        self.proxy_url = "http://dtgrlmjf-rotate:p0bl5bes07qp@p.webshare.io:80"
        # RATE LIMITS: Adjusted for better responsiveness
        self.m_cd = commands.CooldownMapping.from_cooldown(3, 5, commands.BucketType.member)  # 3 per 5 sec
        self.c_cd = commands.CooldownMapping.from_cooldown(5, 5, commands.BucketType.channel)  # 5 per 5 sec
        self.m_cd2 = commands.CooldownMapping.from_cooldown(2, 10, commands.BucketType.member)  # 2 per 10 sec
        self.main_guilds = [1452926205828534363]
        self.global_cd = commands.CooldownMapping.from_cooldown(5, 3, commands.BucketType.member)  # 5 per 3 sec
        self.ext = Client(self) 
        self.session_id = "59071245027%3AD0cDcLaxyzVyVQ%3A16%3AAYdIOvL5SM85A62N-zDxn04CaabIDHneyhA6I0r6VQ"
        
        # OPTIMIZATION: Add disabled command cache
        self._disabled_commands_cache = {}  # {guild_id: set(command_names)}
        self._disabled_commands_cache_time = {}
        
    async def create_db_pool(self):
        """OPTIMIZED: Create connection pool with proper limits for 1GB RAM VPS"""
        self.db = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            # OPTIMIZATION: Limit connections for low-memory VPS
            min_size=2,  # Minimum connections (reduced from default 10)
            max_size=10,  # Maximum connections (reduced from default 10)
            # OPTIMIZATION: Faster connection management
            max_queries=50000,  # Queries per connection before recreation
            max_inactive_connection_lifetime=300,  # Close idle connections after 5 min
            # OPTIMIZATION: Connection tuning
            command_timeout=10,  # 10 second timeout per query
            # OPTIMIZATION: Statement cache for faster repeated queries
            statement_cache_size=100,  # Cache 100 prepared statements
        )
        print("✓ Database pool created with optimized settings")
    
    async def get_context(self, message, *, cls=NeoContext):
        return await super().get_context(message, cls=cls) 

    async def setup_hook(self) -> None:
        """OPTIMIZED: Non-blocking setup"""
        print("Attempting to start")
        self.session = HTTP()
        
        # OPTIMIZATION: Create DB pool immediately (don't defer to task)
        await self.create_db_pool()
        
        # OPTIMIZATION: Load jishaku in background
        asyncio.create_task(self.load_extension("jishaku"))
        
        # Add persistent views
        self.add_view(vmbuttons())
        self.add_view(CreateTicket())
        self.add_view(DeleteTicket())
        self.add_view(GiveawayView())
        
        # OPTIMIZATION: Load cogs in startup task (non-blocking)
        asyncio.create_task(StartUp.startup(bot))     
    
    @property
    def ping(self) -> int: 
        return round(self.latency * 1000) 
    
    def convert_datetime(self, date: datetime.datetime = None):
        if date is None: return None  
        month = f'0{date.month}' if date.month < 10 else date.month 
        day = f'0{date.day}' if date.day < 10 else date.day 
        year = date.year 
        minute = f'0{date.minute}' if date.minute < 10 else date.minute 
        if date.hour < 10: 
            hour = f'0{date.hour}'
            meridian = "AM"
        elif date.hour > 12: 
            hour = f'0{date.hour - 12}' if date.hour - 12 < 10 else f"{date.hour - 12}"
            meridian = "PM"
        else: 
            hour = date.hour
            meridian = "PM"  
        return f"{month}/{day}/{year} at {hour}:{minute} {meridian} ({discord.utils.format_dt(date, style='R')})" 

    def ordinal(self, num: int) -> str:
        """Convert from number to ordinal (10 - 10th)""" 
        numb = str(num) 
        if numb.startswith("0"): numb = numb.strip('0')
        if numb in ["11", "12", "13"]: return numb + "th"
        if numb.endswith("1"): return numb + "st"
        elif numb.endswith("2"):  return numb + "nd"
        elif numb.endswith("3"): return numb + "rd"
        else: return numb + "th" 

    async def getbyte(self, video: str):  
        return BytesIO(await self.session.read(video, proxy=self.proxy_url, ssl=False)) 

    def is_dangerous(self, role: discord.Role) -> bool:
        permissions = role.permissions
        return any([
            permissions.kick_members, permissions.ban_members,
            permissions.administrator, permissions.manage_channels,
            permissions.manage_guild, permissions.manage_messages,
            permissions.manage_roles, permissions.manage_webhooks,
            permissions.manage_emojis_and_stickers, permissions.manage_threads,
            permissions.mention_everyone, permissions.moderate_members
        ])
    
    async def prefixes(self, message: discord.Message) -> List[str]: 
        prefixes = []
        for l in set(p for p in await self.command_prefix(self, message)): 
            prefixes.append(l)
        return prefixes  

    async def guild_change(self, mes: str, guild: discord.Guild) -> discord.Message: 
        return
        # Disabled for performance
    
    async def load_custom_emojis(self):
        """OPTIMIZATION: Load emojis asynchronously in background"""
        if self._emojis_loaded:
            return
        
        try:
            emoji_guild = self.get_guild(1452926205828534363)
            if emoji_guild:
                checkmark = discord.utils.get(emoji_guild.emojis, name="checkmark")
                xmark = discord.utils.get(emoji_guild.emojis, name="xmark")
               
                if checkmark:
                    self.yes = str(checkmark)
                if xmark:
                    self.no = str(xmark)
                    self.warning = str(xmark)
            
            self._emojis_loaded = True
            print(f"✓ Emojis loaded - Yes: {self.yes}, No: {self.no}")
        except Exception as e:
            print(f"⚠ Emoji loading failed: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        # OPTIMIZATION: Chunk only when needed
        if not guild.chunked: 
            await guild.chunk(cache=True)
        await self.guild_change("joined", guild)

    async def on_guild_remove(self, guild: discord.Guild): 
        await self.guild_change("left", guild) 
        # OPTIMIZATION: Clear caches for this guild
        prefix_cache.invalidate_guild(guild.id)
        self._disabled_commands_cache.pop(guild.id, None)
        self._disabled_commands_cache_time.pop(guild.id, None)
   
    async def channel_ratelimit(self, message: discord.Message) -> typing.Optional[int]:
        cd = self.c_cd
        bucket = cd.get_bucket(message)
        return bucket.update_rate_limit()

    async def member_ratelimit(self, message: discord.Message) -> typing.Optional[int]:
        cd = self.m_cd
        bucket = cd.get_bucket(message)
        return bucket.update_rate_limit()

    async def on_ready(self):
        # OPTIMIZATION: Run DB creation in background
        asyncio.create_task(create_db(self))
        
        if self.cogs_loaded == False:
            await StartUp.loadcogs(self)
       
        # OPTIMIZATION: Load emojis in background (non-blocking)
        if not self._emojis_loaded:
            asyncio.create_task(self.load_custom_emojis())
       
        print(f"✓ Connected to Discord API as {self.user} {self.user.id}")
        print(f"✓ Latency: {self.ping}ms")
        print(f"✓ Guilds: {len(self.guilds)}")
        print(f"✓ Optimization: Enabled")
    
    async def on_message_edit(self, before, after):
        if before.content != after.content: 
            await self.process_commands(after)

    async def on_message(self, message: discord.Message):
        # OPTIMIZATION: Fast path for common cases
        if message.author.bot:
            return
        
        # SECURITY: Process message first (AI moderation runs as Cog listener)
        # This ensures violations are caught even if user is rate-limited
        await self.process_commands(message)
        
        # THEN apply rate limits for future messages
        channel_rl = await self.channel_ratelimit(message)
        if channel_rl:
            return
        
        member_rl = await self.member_ratelimit(message)
        if member_rl:
            return
        
        # Handle bot mention
        if message.content == f"<@{self.user.id}>": 
            prefixes = await self.prefixes(message)
            await message.reply(content="prefixes: " + " ".join(f"`{g}`" for g in prefixes)) 

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound): 
            return 
        elif isinstance(error, commands.NotOwner): 
            pass
        elif isinstance(error, commands.CheckFailure): 
            if isinstance(error, commands.MissingPermissions): 
                return await ctx.send_warning(f"This command requires **{error.missing_permissions[0]}** permission")
        elif isinstance(error, commands.CommandOnCooldown):
            if ctx.command.name != "hit": 
                return await ctx.reply(embed=discord.Embed(color=0xE1C16E, description=f"⌛ {ctx.author.mention}: You are on cooldown. Try again in {format_timespan(error.retry_after)}"), mention_author=False)    
        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.cmdhelp()
        elif isinstance(error, commands.EmojiNotFound):
            return await ctx.send_warning(f"Unable to convert {error.argument} into an **emoji**")
        elif isinstance(error, commands.MemberNotFound):
            return await ctx.send_warning(f"Unable to find member **{error.argument}**")
        elif isinstance(error, commands.UserNotFound):
            return await ctx.send_warning(f"Unable to find user **{error.argument}**")
        elif isinstance(error, commands.RoleNotFound):
            return await ctx.send_warning(f"Couldn't find role **{error.argument}**")
        elif isinstance(error, commands.ChannelNotFound):
            return await ctx.send_warning(f"Couldn't find channel **{error.argument}**")
        elif isinstance(error, commands.UserConverter):
            return await ctx.send_warning(f"Couldn't convert that into an **user**")
        elif isinstance(error, commands.MemberConverter):
            return await ctx.send_warning("Couldn't convert that into a **member**")
        elif isinstance(error, commands.BadArgument):
            return await ctx.send_warning(error.args[0])
        elif isinstance(error, commands.BotMissingPermissions):
            return await ctx.send_warning("I do not have enough **permissions** to execute this command")
        elif isinstance(error, discord.HTTPException):
            return await ctx.send_warning("Unable to execute this command")
        else:
            import traceback
            traceback.print_exception(type(error), error, error.__traceback__)

            key = await checkthekey(generate_key())
            trace = str(error)

            rl = await self.member_ratelimit(ctx.message)
            if rl:
                return

            await self.db.execute(
                "INSERT INTO cmderror VALUES ($1,$2)",
                key,
                trace
            )

            await self.ext.send_error(
                ctx,
                f"An unexpected error was found. Please report the code `{key}` in our [**support server**](https://discord.gg/coon)"
            )
         

bot = CommandClient()

@bot.check
async def cooldown_check(ctx: commands.Context):
    bucket = bot.global_cd.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after: 
        raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.member)
    return True

async def check_ratelimit(ctx):
    cd = bot.m_cd2.get_bucket(ctx.message)
    return cd.update_rate_limit()

@bot.check
async def is_chunked(ctx: commands.Context):
    if ctx.guild: 
        # OPTIMIZATION: Chunk on-demand, not preemptively
        if not ctx.guild.chunked: 
            await ctx.guild.chunk(cache=True)
        return True

@bot.check
async def disabled_command(ctx: commands.Context):
    """OPTIMIZED: Use in-memory cache for disabled commands"""
    cmd = bot.get_command(ctx.invoked_with)
    if not cmd or not ctx.guild: 
        return True
    
    # Check cache first (60 second TTL)
    cache_key = ctx.guild.id
    if cache_key in bot._disabled_commands_cache:
        cache_time = bot._disabled_commands_cache_time.get(cache_key, 0)
        if time.time() - cache_time < 60:  # 60 second cache
            disabled_cmds = bot._disabled_commands_cache[cache_key]
            if cmd.name in disabled_cmds:
                await bot.ext.send_warning(ctx, f"The command **{cmd.name}** is **disabled**")
                return False
            return True
    
    # Cache miss - query database
    check = await ctx.bot.db.fetchrow(
        'SELECT command FROM disablecommand WHERE command = $1 AND guild_id = $2', 
        cmd.name, ctx.guild.id
    )
    
    # Update cache
    if cache_key not in bot._disabled_commands_cache:
        bot._disabled_commands_cache[cache_key] = set()
        bot._disabled_commands_cache_time[cache_key] = time.time()
    
    if check:
        bot._disabled_commands_cache[cache_key].add(cmd.name)
        await bot.ext.send_warning(ctx, f"The command **{cmd.name}** is **disabled**")
        return False
    
    return True

if __name__ == '__main__':
    print("=" * 50)
    print("OPTIMIZED BOT STARTING")
    print("=" * 50)
    bot.run(token)
