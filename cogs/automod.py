import discord, datetime, asyncio, logging
from discord.ext import commands 
from cogs.utility import DISCORD_API_LINK
from tools.checks import Perms
from tools.utils import Whitelist

logger = logging.getLogger(__name__)

async def decrypt_message(content: str) -> str: 
  return content.lower().replace("1", "i").replace("4", "a").replace("3", "e").replace("0", "o").replace("@", "a") 

class AutoMod(commands.Cog): 
    def __init__(self, bot: commands.AutoShardedBot): 
      self.bot = bot 
      self.antispam_cache = {}
      self._db_timeout = 5.0  # 5 second timeout for DB operations

    async def _db_fetchrow(self, query: str, *args, timeout: float = None):
        """Wrapper for DB fetchrow with timeout and error handling"""
        try:
            return await asyncio.wait_for(
                self.bot.db.fetchrow(query, *args),
                timeout=timeout or self._db_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"DB timeout on query: {query[:50]}...")
            return None
        except Exception as e:
            logger.error(f"DB error on query: {query[:50]}... - {e}")
            return None

    @commands.Cog.listener('on_message')
    async def antispam_send(self, message: discord.Message): 
     if not message.guild: return 
     if isinstance(message.author, discord.User): return 
     # OPTIMIZATION: Direct permission check instead of get_context (which triggers DB prefix lookup)
     if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_guild: return 
     
     # OPTIMIZATION: Check cache first
     from entry import guild_config_cache
     check = guild_config_cache.get_antispam(message.guild.id)
     if check is None:
         check = await self._db_fetchrow("SELECT * FROM antispam WHERE guild_id = $1", message.guild.id)
         guild_config_cache.set_antispam(message.guild.id, check)
     
     if check: 
      # OPTIMIZATION: Check whitelist cache first
      res1 = guild_config_cache.get_whitelist(message.guild.id, "antispam", message.channel.id, "channel")
      if res1 is None:
          row = await self._db_fetchrow("SELECT 1 FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "antispam", message.channel.id, "channel")
          res1 = row is not None
          guild_config_cache.set_whitelist(message.guild.id, "antispam", message.channel.id, "channel", res1)
      
      if not res1:  
          res2 = guild_config_cache.get_whitelist(message.guild.id, "antispam", message.author.id, "user")
          if res2 is None:
              row = await self._db_fetchrow("SELECT 1 FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "antispam", message.author.id, "user")
              res2 = row is not None
              guild_config_cache.set_whitelist(message.guild.id, "antispam", message.author.id, "user", res2)
          
          if not res2: 
           if not self.antispam_cache.get(str(message.channel.id)): self.antispam_cache[str(message.channel.id)] = {}
           if not self.antispam_cache[str(message.channel.id)].get(str(message.author.id)): self.antispam_cache[str(message.channel.id)][str(message.author.id)] = []
           self.antispam_cache[str(message.channel.id)][str(message.author.id)].append(tuple([datetime.datetime.now(), message]))
           expired_time = check["seconds"]
           expired_msgs = [msg for msg in self.antispam_cache[str(message.channel.id)][str(message.author.id)] if (datetime.datetime.now()-msg[0]).total_seconds() > expired_time]
           for ex in expired_msgs: self.antispam_cache[str(message.channel.id)][str(message.author.id)].remove(ex)
           if len(self.antispam_cache[str(message.channel.id)][str(message.author.id)]) > check["count"]: 
            messages = [msg[1] for msg in self.antispam_cache[str(message.channel.id)][str(message.author.id)]]
            self.antispam_cache[str(message.channel.id)][str(message.author.id)] = []
            punishment = check["punishment"]
            if punishment == "delete": return await message.channel.delete_messages(messages, reason="AutoMod: spamming messages")
            await message.channel.delete_messages(messages, reason="AutoMod: spamming messages")
            if not message.author.is_timed_out(): 
              await message.channel.send(embed=discord.Embed(color=self.bot.color, title="AutoMod", description=f"{self.bot.warning} {message.author.mention}: You have been muted for **1 minute** for spamming messages in this channel"))     
              await message.author.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=1), reason="AutoMod: spamming messages")

    @commands.Cog.listener('on_message')
    async def chatfilter_send(self, message: discord.Message): 
      if not message.guild: return 
      if isinstance(message.author, discord.User): return 
      # OPTIMIZATION: Direct permission check
      if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_guild: return 
      
      # OPTIMIZATION: Check cache first
      from entry import guild_config_cache
      words = guild_config_cache.get_chatfilter(message.guild.id)
      if words is None:
          check = await self.bot.db.fetch("SELECT word FROM chatfilter WHERE guild_id = $1", message.guild.id)
          words = [row['word'] for row in check]
          guild_config_cache.set_chatfilter(message.guild.id, words)
      
      if not words:
          return
      
      # OPTIMIZATION: Cache whitelist checks
      res1 = guild_config_cache.get_whitelist(message.guild.id, "chatfilter", message.channel.id, "channel")
      if res1 is None:
          row = await self.bot.db.fetchrow("SELECT 1 FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "chatfilter", message.channel.id, "channel")
          res1 = row is not None
          guild_config_cache.set_whitelist(message.guild.id, "chatfilter", message.channel.id, "channel", res1)
      
      if res1:
          return
      
      res2 = guild_config_cache.get_whitelist(message.guild.id, "chatfilter", message.author.id, "user")
      if res2 is None:
          row = await self.bot.db.fetchrow("SELECT 1 FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "chatfilter", message.author.id, "user")
          res2 = row is not None
          guild_config_cache.set_whitelist(message.guild.id, "chatfilter", message.author.id, "user", res2)
      
      if res2:
          return
      
      # Check message content
      decrypted = await decrypt_message(message.content)
      for word in words:
          if word in decrypted:
              try:
                  await message.delete()
              except (discord.NotFound, discord.Forbidden):
                  pass
              return                          
    
    @commands.Cog.listener('on_message_edit')
    async def chatfilter_edit(self, before, after: discord.Message): 
      if before.content == after.content: return 
      message = after 
      if not message.guild: return 
      if isinstance(message.author, discord.User): return 
      # OPTIMIZATION: Direct permission check
      if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_guild: return 
      
      # OPTIMIZATION: Check cache first
      from entry import guild_config_cache
      words = guild_config_cache.get_chatfilter(message.guild.id)
      if words is None:
          check = await self.bot.db.fetch("SELECT word FROM chatfilter WHERE guild_id = $1", message.guild.id)
          words = [row['word'] for row in check]
          guild_config_cache.set_chatfilter(message.guild.id, words)
      
      if not words:
          return
      
      # OPTIMIZATION: Cache whitelist checks
      res1 = guild_config_cache.get_whitelist(message.guild.id, "chatfilter", message.channel.id, "channel")
      if res1 is None:
          row = await self.bot.db.fetchrow("SELECT 1 FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "chatfilter", message.channel.id, "channel")
          res1 = row is not None
          guild_config_cache.set_whitelist(message.guild.id, "chatfilter", message.channel.id, "channel", res1)
      
      if res1:
          return
      
      res2 = guild_config_cache.get_whitelist(message.guild.id, "chatfilter", message.author.id, "user")
      if res2 is None:
          row = await self.bot.db.fetchrow("SELECT 1 FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "chatfilter", message.author.id, "user")
          res2 = row is not None
          guild_config_cache.set_whitelist(message.guild.id, "chatfilter", message.author.id, "user", res2)
      
      if res2:
          return
      
      # Check message content
      decrypted = await decrypt_message(message.content)
      for word in words:
          if word in decrypted:
              try:
                  await message.delete()
              except (discord.NotFound, discord.Forbidden):
                  pass
              return     

    @commands.Cog.listener('on_message_edit')
    async def invite_edit(self, before, after: discord.Message): 
      if after.content == before.content: return
      message = after
      if not message.guild: return
      if isinstance(message.author, discord.User): return
      if message.author.bot: return
      if await Perms.has_perms(await self.bot.get_context(message), "manage_guild"): return
      invites = ["discord.gg/", ".gg/", "discord.com/invite/"]
      if any(invite in message.content for invite in invites):
          check = await self.bot.db.fetchrow("SELECT * FROM antiinvite WHERE guild_id = $1", message.guild.id)
          if check is not None:
              res1 = await self.bot.db.fetchrow("SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "antiinvite", message.channel.id, "channel")
              if res1: return
              res2 = await self.bot.db.fetchrow("SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "antiinvite", message.author.id, "user")
              if res2: return
              spl_word = None
              for inv in invites:
                  if inv in message.content:
                      spl_word = inv
                      break
              if not spl_word: return
              linko = message.content.partition(spl_word)[2]
              invite_code = linko.split()[0]
              try:
                  if invite_code.lower() in [message.guild.id, str(message.guild.id)]: return
                  await message.delete()
                  await message.author.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=1), reason="AutoMod: Sending invites")
                  await message.channel.send(embed=discord.Embed(color=self.bot.color, title="AutoMod", description=f"{self.bot.warning} {message.author.mention}: You have been muted for **1 minute** for sending discord invites in this channel"))
              except Exception: pass
  

    @commands.Cog.listener('on_message')
    async def invite_send(self, message: discord.Message):   
        if not message.guild: return
        if isinstance(message.author, discord.User): return
        if message.author.bot: return
        if await Perms.has_perms(await self.bot.get_context(message), "manage_guild"): return
        invites = ["discord.gg/", ".gg/", "discord.com/invite/"]
        if any(invite in message.content for invite in invites):
            check = await self.bot.db.fetchrow("SELECT * FROM antiinvite WHERE guild_id = $1", message.guild.id)
            if check is not None:
                res1 = await self.bot.db.fetchrow("SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "antiinvite", message.channel.id, "channel")
                if res1: return
                res2 = await self.bot.db.fetchrow("SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4", message.guild.id, "antiinvite", message.author.id, "user")
                if res2: return
                spl_word = None
                for inv in invites:
                    if inv in message.content:
                        spl_word = inv
                        break
                if not spl_word: return
                linko = message.content.partition(spl_word)[2]
                invite_code = linko.split()[0]
                try:
                    if invite_code.lower() in [message.guild.id, str(message.guild.id)]: return
                    await message.delete()
                    await message.author.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=5), reason="AutoMod: Sending invites")
                    await message.channel.send(embed=discord.Embed(color=self.bot.color, title="AutoMod", description=f"{self.bot.warning} {message.author.mention}: You have been muted for **5 minutes** for sending discord invites in this channel"))
                except Exception: pass
  
    
    @commands.hybrid_group(aliases=["cf"], invoke_without_command=True)
    async def chatfilter(self, ctx): 
      await ctx.create_pages()

    @chatfilter.command(name="add", description="add a word to the chatfilter", help="automod", brief="manage guild", usage="[word]")
    @Perms.get_perms("manage_guild")  
    async def cf_add(self, ctx: commands.Context, *, word: str): 
     check = await self.bot.db.fetchrow("SELECT * FROM chatfilter WHERE guild_id = $1 AND word = $2", ctx.guild.id, word.lower())
     if check: return await ctx.send_warning("This word is **already** added in the chatfilter list") 
     await self.bot.db.execute("INSERT INTO chatfilter VALUES ($1,$2)", ctx.message.guild.id, word.lower())
     # Invalidate cache
     from entry import guild_config_cache
     guild_config_cache.invalidate_chatfilter(ctx.guild.id)
     await ctx.send_success(f"Added **{word}** as a filtered word")
    
    @chatfilter.command(name="remove", description="remove a word from the chatfilter", help="automod", brief="manage guild", usage="[word]")
    @Perms.get_perms("manage_guild")
    async def cf_remove(self, ctx: commands.Context, *, word: str): 
     check = await self.bot.db.fetchrow("SELECT * FROM chatfilter WHERE guild_id = $1 AND word = $2", ctx.guild.id, word.lower())
     if not check: return await ctx.send_warning("This word is **not** added in the chatfilter list") 
     await self.bot.db.execute("DELETE FROM chatfilter WHERE guild_id = $1 AND word = $2", ctx.message.guild.id, word.lower())
     # Invalidate cache
     from entry import guild_config_cache
     guild_config_cache.invalidate_chatfilter(ctx.guild.id)
     await ctx.send_success(f"Removed **{word}** from the filtered word") 
    
    @chatfilter.command(name="list", description="returns a list of blacklisted words", help="automod")
    async def cf_list(self, ctx: commands.Context):
     results = await self.bot.db.fetch("SELECT * FROM chatfilter WHERE guild_id = $1", ctx.guild.id)
     if len(results) == 0: return await ctx.send_warning("No **blacklisted** words found")
     i=0
     k=1
     l=0
     mes = ""
     number = []
     messages = []
     for result in results:
       mes = f"{mes}`{k}` {result['word']}\n"
       k+=1
       l+=1
       if l == 10:
         messages.append(mes)
         number.append(discord.Embed(color=self.bot.color, title=f"blacklisted words ({len(results)})", description=messages[i]))
         i+=1
         mes = ""
         l=0
    
     messages.append(mes)
     number.append(discord.Embed(color=self.bot.color, title=f"blacklisted words ({len(results)})", description=messages[i]))     
     await ctx.paginator(number) 
    
    @chatfilter.group(name="whitelist", description="manage whitelist for chatfilter", help="automod", aliases=["wl"])
    async def cf_whitelist(self, ctx: commands.Context): 
      await ctx.create_pages()

    @cf_whitelist.command(brief="manage guild", description="whitelist a channel from chatfilter", help="automod", name="channel")
    @Perms.get_perms("manage_guild")  
    async def cf_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
     await Whitelist.whitelist_things(ctx, "chatfilter", channel)    

    @cf_whitelist.command(brief="manage guild", description="whitelist an user from chatfilter", help="automod", name="user")
    @Perms.get_perms("manage_guild")  
    async def cf_user(self, ctx: commands.Context, *, member: discord.Member): 
      await Whitelist.whitelist_things(ctx, "chatfilter", member)
    
    @chatfilter.group(name="unwhitelist", description="remove channels or users from chatfilter whitelist", help="automod", aliases=["uwl"])
    async def cf_unwhitelist(self, ctx): 
      await ctx.create_pages()
    
    @cf_unwhitelist.command(help="automod", name="channel", description="unwhitelist a channel from chatfilter", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def cf_unwhitelist_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
     await Whitelist.unwhitelist_things(ctx, "chatfilter", channel)
    
    @cf_unwhitelist.command(help="automod", name="user", description="unwhitelist an user from chatfilter", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def cf_unwhitelist_user(self, ctx: commands.Context, *, member: discord.Member):
     await Whitelist.unwhitelist_things(ctx, "chatfilter", member)     
    
    @chatfilter.group(name="whitelisted", description="returns a list of whitelisted channels or users", help="automod")
    async def cf_whitelisted(self, ctx: commands.Context): 
      await ctx.create_pages()

    @cf_whitelisted.command(name="channels", help="automod", description="return a list of whitelisted channels")
    async def cf_whitelisted_channels(self, ctx: commands.Context): 
     await Whitelist.whitelisted_things(ctx, "chatfilter", "channel") 

    @cf_whitelisted.command(name="users", description="return a list of whitelisted users", help="automod")
    async def whitelisted_users(self, ctx: commands.Context): 
      await Whitelist.whitelisted_things(ctx, "chatfilter", "user")
    
    @commands.hybrid_group(name="antispam", invoke_without_command=True)
    async def anti_spam(self, ctx): 
      return await ctx.create_pages() 

    @anti_spam.command(name="enable", description="enable anti spam", aliases=['e'], help="automod", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def anti_spam_enable(self, ctx: commands.Context):       
        check = await self.bot.db.fetchrow("SELECT * FROM antispam WHERE guild_id = {}".format(ctx.guild.id))        
        if check: return await ctx.send_error("Anti-spam is **already** enabled")
        await self.bot.db.execute("INSERT INTO antispam VALUES ($1,$2,$3,$4)", ctx.guild.id, 5, 5, "mute")
        # Invalidate cache
        from entry import guild_config_cache
        guild_config_cache.invalidate_antispam(ctx.guild.id)
        return await ctx.send_success("Anti-spam is now enabled")
    
    @anti_spam.command(name="disable", description="disable anti spam", help="automod", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def anti_spam_disable(self, ctx: commands.Context):
      check = await self.bot.db.fetchrow("SELECT * FROM antispam WHERE guild_id = {}".format(ctx.guild.id))        
      if not check: return await ctx.send_error("Anti-spam is **not** enabled")
      await self.bot.db.execute("DELETE FROM antispam WHERE guild_id = $1", ctx.guild.id)
      # Invalidate cache
      from entry import guild_config_cache
      guild_config_cache.invalidate_antispam(ctx.guild.id)
      return await ctx.send_success("Anti-spam is now disabled") 
    
    @anti_spam.command(name="punishment", description="set antispam punishment", help="automod", brief="manage guild", usage="[punishment]")
    @Perms.get_perms("manage_guild")
    async def anti_spam_punishment(self, ctx: commands.Context, punishment: str): 
     check = await self.bot.db.fetchrow("SELECT * FROM antispam WHERE guild_id = {}".format(ctx.guild.id))        
     if not check: return await ctx.send_error("Anti-spam is **not** enabled") 
     if not punishment in ["delete", "mute"]: return await ctx.send_warning(f"Punishment can be only **ban** or **mute**, not **{punishment}**") 
     await self.bot.db.execute("UPDATE antispam SET punishment = $1 WHERE guild_id = $2", punishment, ctx.guild.id)
     # Invalidate cache
     from entry import guild_config_cache
     guild_config_cache.invalidate_antispam(ctx.guild.id)
     return await ctx.send_success(f"Anti-spam punishment set to **{punishment}**") 
    
    @anti_spam.command(name="seconds", description="set antispam's delay time", help="automod", brief="manage guild", usage="[seconds]")
    @Perms.get_perms("manage_guild")
    async def anti_spam_seconds(self, ctx: commands.Context, second: int): 
     check = await self.bot.db.fetchrow("SELECT * FROM antispam WHERE guild_id = {}".format(ctx.guild.id))        
     if not check: return await ctx.send_error("Anti-spam is **not** enabled") 
     if second < 1: return await ctx.send_warning(f"Anti-spam delay can't be lower than 1 second") 
     await self.bot.db.execute("UPDATE antispam SET seconds = $1 WHERE guild_id = $2", second, ctx.guild.id)
     # Invalidate cache
     from entry import guild_config_cache
     guild_config_cache.invalidate_antispam(ctx.guild.id)
     return await ctx.send_success(f"Anti-spam delay set to **{second}**")  
    
    @anti_spam.command(name="limit", description="set antispam's limit", help="automod", brief="manage guild", usage="[limit]")
    @Perms.get_perms("manage_guild")
    async def anti_spam_limit(self, ctx: commands.Context, second: int): 
     check = await self.bot.db.fetchrow("SELECT * FROM antispam WHERE guild_id = {}".format(ctx.guild.id))        
     if not check: return await ctx.send_error("Anti-spam is **not** enabled") 
     if second < 1: return await ctx.send_warning(f"Anti-spam limit can't be lower than 1 second") 
     await self.bot.db.execute("UPDATE antispam SET count = $1 WHERE guild_id = $2", second, ctx.guild.id)
     # Invalidate cache
     from entry import guild_config_cache
     guild_config_cache.invalidate_antispam(ctx.guild.id)
     return await ctx.send_success(f"Anti-spam limit set to **{second}**")
    
    @anti_spam.group(name="whitelist", description="manage whitelist for anti spam", help="automod", aliases=["wl"])
    async def antispam_whitelist(self, ctx: commands.Context): 
      await ctx.create_pages()

    @antispam_whitelist.command(brief="manage guild", description="whitelist a channel from anti spam", help="automod", name="channel")
    @Perms.get_perms("manage_guild")  
    async def antispam_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
     await Whitelist.whitelist_things(ctx, "antispam", channel)    

    @antispam_whitelist.command(brief="manage guild", description="whitelist an user from anti spam", help="automod", name="user")
    @Perms.get_perms("manage_guild")  
    async def antispam_user(self, ctx: commands.Context, *, member: discord.Member): 
      await Whitelist.whitelist_things(ctx, "antispam", member)
    
    @anti_spam.group(name="unwhitelist", description="remove channels or users from antispam whitelist", help="automod", aliases=["uwl"])
    async def antispam_unwhitelist(self, ctx): 
      await ctx.create_pages()
    
    @antispam_unwhitelist.command(help="automod", name="channel", description="unwhitelist a channel from anti spam", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def as_unwhitelist_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
     await Whitelist.unwhitelist_things(ctx, "antispam", channel)
    
    @antispam_unwhitelist.command(help="automod", name="user", description="unwhitelist an user from anti spam", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def as_unwhitelist_user(self, ctx: commands.Context, *, channel: discord.Member):
     await Whitelist.unwhitelist_things(ctx, "antispam", channel)     
    
    @anti_spam.group(name="whitelisted", description="returns a list of whitelisted channels or users", help="automod")
    async def antispam_whitelisted(self, ctx: commands.Context): 
      await ctx.create_pages()

    @antispam_whitelisted.command(name="channels", help="automod", description="return a list of whitelisted channels")
    async def as_whitelisted_channels(self, ctx: commands.Context): 
     await Whitelist.whitelisted_things(ctx, "antispam", "channel") 

    @antispam_whitelisted.command(name="users", description="return a list of whitelisted users", help="automod")
    async def as_whitelisted_users(self, ctx: commands.Context): 
      await Whitelist.whitelisted_things(ctx, "antispam", "user")

    @commands.hybrid_group(name="anti-invite", invoke_without_command=True, aliases=["antilink", "anti-link"])
    async def anti_invite(self, ctx: commands.Context): 
     await ctx.create_pages()

    @anti_invite.command(name="enable", description="enable anti invite", aliases=["e"], help="automod", brief="manage guild") 
    @Perms.get_perms("manage_guild")
    async def antiinvite_enable(self, ctx: commands.Context):      
        check = await self.bot.db.fetchrow("SELECT * FROM antiinvite WHERE guild_id = {}".format(ctx.guild.id))        
        if check: return await ctx.send_error("Anti-invite is **already** enabled")
        await self.bot.db.execute("INSERT INTO antiinvite VALUES ($1)", ctx.guild.id)
        return await ctx.send_success("Anti-invite is now enabled")
    
    @anti_invite.command(name="disable", description="disable anti invite", aliases=["d"], help="automod") 
    @Perms.get_perms("manage_guild")
    async def antiinvite_disable(self, ctx: commands.Context): 
        check = await self.bot.db.fetchrow("SELECT * FROM antiinvite WHERE guild_id = {}".format(ctx.guild.id))        
        if not check: return await ctx.send_error("Anti-invite is **not** enabled")
        await self.bot.db.execute("DELETE FROM antiinvite WHERE guild_id = $1", ctx.guild.id)
        return await ctx.send_success("Anti-invite is now disabled")
    
    @anti_invite.group(name="whitelist", description="manage whitelist for anti invite", help="automod", aliases=["wl"])
    async def antiinvite_whitelist(self, ctx: commands.Context): 
      await ctx.create_pages()

    @antiinvite_whitelist.command(brief="manage guild", description="whitelist a channel from anti invite", help="automod", name="channel")
    @Perms.get_perms("manage_guild")  
    async def antiinvite_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
     await Whitelist.whitelist_things(ctx, "antiinvite", channel)    

    @antiinvite_whitelist.command(brief="manage guild", description="whitelist an user from antiinvite", help="automod", name="user")
    @Perms.get_perms("manage_guild")  
    async def antiinvite_user(self, ctx: commands.Context, *, member: discord.Member): 
      await Whitelist.whitelist_things(ctx, "antiinvite", member)
    
    @anti_invite.group(name="unwhitelist", description="remove channels or users from antilink whitelist", help="automod", aliases=["uwl"])
    async def antiinvite_unwhitelist(self, ctx): 
      await ctx.create_pages()
    
    @antiinvite_unwhitelist.command(help="automod", name="channel", description="unwhitelist a channel from antiinvite", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def unwhitelist_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
     await Whitelist.unwhitelist_things(ctx, "antiinvite", channel)
    
    @antiinvite_unwhitelist.command(help="automod", name="user", description="unwhitelist an user from antiinvite", brief="manage guild")
    @Perms.get_perms("manage_guild")
    async def unwhitelist_user(self, ctx: commands.Context, *, channel: discord.Member):
     await Whitelist.unwhitelist_things(ctx, "antiinvite", channel)     
    
    @anti_invite.group(name="whitelisted", description="returns a list of whitelisted channels or users", help="automod")
    async def antiinvite_whitelisted(self, ctx: commands.Context): 
      await ctx.create_pages()

    @antiinvite_whitelisted.command(name="channels", help="automod", description="return a list of whitelisted channels")
    async def whitelisted_channels(self, ctx: commands.Context): 
     await Whitelist.whitelisted_things(ctx, "antiinvite", "channel") 

    @antiinvite_whitelisted.command(name="users", description="return a list of whitelisted users", help="automod")
    async def whitelisted_users(self, ctx: commands.Context): 
      await Whitelist.whitelisted_things(ctx, "antiinvite", "user")

async def setup(bot): 
    await bot.add_cog(AutoMod(bot))        
