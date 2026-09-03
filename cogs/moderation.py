import discord, datetime, humanfriendly, json 
from discord.ext import commands 
from typing import Union
from uwuipy import Uwuipy
from tools.checks import Mod
from cogs.config import InvokeClass
from tools.utils import EmbedBuilder, GoodRole, NoStaff
from tools.checks import Perms


async def uwuthing(bot, text: str) -> str:
    uwu = Uwuipy()
    return uwu.uwuify(text)


class ClearMod(discord.ui.View): 
  def __init__(self, ctx: commands.Context): 
   super().__init__()
   self.ctx = ctx
   self.status = False

   

  @discord.ui.button(emoji="<:check2:1035581286011646004>")
  async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
   if interaction.user.id != self.ctx.author.id: return await interaction.client.ext.send_warning(interaction, "You are not the author of this embed")
   check = await interaction.client.db.fetchrow("SELECT * FROM mod WHERE guild_id = $1", interaction.guild.id)     
   channelid = check["channel_id"]
   roleid = check["role_id"]
   logsid = check["jail_id"]
   channel = interaction.guild.get_channel(channelid)
   role = interaction.guild.get_role(roleid)
   logs = interaction.guild.get_channel(logsid)
   try: await channel.delete()
   except: pass 
   try: await role.delete()
   except: pass
   try: await logs.delete()
   except: pass 
   await interaction.client.db.execute("DELETE FROM mod WHERE guild_id = $1", interaction.guild.id)
   self.status = True
   return await interaction.response.edit_message(view=None, embed=discord.Embed(color=interaction.client.color, description=f"{interaction.client.yes} {interaction.user.mention}: Disabled moderation"))
  
  @discord.ui.button(emoji="<:stop:1018156487232720907>")
  async def no(self, interaction: discord.Interaction, button: discord.ui.Button): 
    if interaction.user.id != self.ctx.author.id: return await interaction.client.ext.send_warning(interaction, "You are not the author of this embed")
    await interaction.response.edit_message(embed=discord.Embed(color=interaction.client.color, description="aborting action"), view=None)
    self.status = True

  async def on_timeout(self) -> None:
       if self.status == False: 
        for item in self.children:
            item.disabled = True

        await self.message.edit(view=self) 

class ModConfig:
 
 async def sendlogs(bot: commands.AutoShardedBot, action: str, author: discord.Member, victim: Union[discord.Member, discord.User], reason: str): 
  check = await bot.db.fetchrow("SELECT channel_id FROM mod WHERE guild_id = $1", author.guild.id)
  if check: 
   res = await bot.db.fetchrow("SELECT count FROM cases WHERE guild_id = $1", author.guild.id)
   case = int(res['count']) + 1 
   await bot.db.execute("UPDATE cases SET count = $1 WHERE guild_id = $2", case, author.guild.id)
   embed = discord.Embed(color=bot.color, title=f"case #{case} ➜ {action}", timestamp=datetime.datetime.now())   
   embed.add_field(name="user", value=f"{victim}\n({victim.id})")
   embed.add_field(name="mod", value=f"{author}\n({author.id})")
   embed.add_field(name="reason", value=reason, inline=False)
   try: await author.guild.get_channel(int(check['channel_id'])).send(embed=embed)
   except: pass
 
 async def send_dm(ctx: commands.Context, member: discord.Member, action: str, reason: str): 
  results = await ctx.bot.db.fetchrow("SELECT * FROM authorize WHERE guild_id = $1", ctx.guild.id)
  if results or ctx.guild.id in ctx.bot.main_guilds: 
   res = await ctx.bot.db.fetchrow("SELECT embed FROM dm WHERE guild_id = $1 AND command = $2", ctx.guild.id, ctx.command.name)   
   if res:
    name = res[0]
    if name.lower() == "off": return
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label=f"sent from {ctx.guild.name}", disabled=True))
    try: 
     x = await EmbedBuilder.to_object(EmbedBuilder.embed_replacement(ctx.author, InvokeClass.invoke_replacement(member, name)).replace("{reason}", reason))
     try: return await member.send(content=x[0], embed=x[1], view=view)
     except: pass
    except Exception as e:
      print(e) 
      try: return await member.send(content=InvokeClass.invoke_replacement(member, EmbedBuilder.embed_replacement(ctx.author, name)).replace('{reason}', reason), embed=None, view=view)    
      except: pass   
   else: 
    embed = discord.Embed(color=ctx.bot.color, description=f"You have been **{action}** in {ctx.guild.name}\n{f'reason: {reason}' if reason != 'No reason provided' else ''}")
    try: await member.send(embed=embed)
    except: pass    
  else:
    embed = discord.Embed(color=ctx.bot.color, description=f"You have been **{action}** in {ctx.guild.name}\n{f'reason: {reason}' if reason != 'No reason provided' else ''}")
    try: await member.send(embed=embed)
    except: pass

class Moderation(commands.Cog): 
  def __init__(self, bot: commands.AutoShardedBot): 
    self.bot = bot


  @commands.Cog.listener()
  async def on_message(self, message: discord.Message):
      if not message.guild:
          return
      if isinstance(message.author, discord.User):
          return
      check = await self.bot.db.fetchrow("SELECT * FROM uwulock WHERE guild_id = $1 AND user_id = $2", message.guild.id, message.author.id)
      if not check:
          return
      try:
          await message.delete()
          uwumsg = await uwuthing(self.bot, message.clean_content)
          webhooks = await message.channel.webhooks()
          webhook = None
          for wh in webhooks:
              if wh.name == "yuki - uwulock":
                  webhook = wh
                  break
          if not webhook:
              webhook = await message.channel.create_webhook(name="yuki - uwulock", reason="for uwulock")
          await webhook.send(content=uwumsg, username=message.author.display_name, avatar_url=message.author.display_avatar.url)
      except Exception as e:
          print(f"[uwulock error] {e}")

  
  @commands.Cog.listener('on_member_remove')
  async def on_restore(self, member: discord.Member):
      check = await self.bot.db.fetchrow("SELECT * FROM nodata WHERE user_id = $1 AND state = $2", member.id, "false")
      if check: return
      list = [role.id for role in member.roles if role.is_assignable()]
      sql_as_text = json.dumps(list)
      ch = await self.bot.db.fetchrow("SELECT * FROM restore WHERE user_id = {} AND guild_id = {}".format(member.id, member.guild.id))   
      if ch: return await self.bot.db.execute("UPDATE restore SET roles = $1 WHERE guild_id = $2 AND user_id = $3", sql_as_text, member.guild.id, member.id)
      return await self.bot.db.execute("INSERT INTO restore VALUES ($1,$2,$3)", member.guild.id, member.id, sql_as_text)
   
  @commands.Cog.listener()
  async def on_guild_channel_create(self, channel):
      check = await self.bot.db.fetchrow("SELECT * FROM mod WHERE guild_id = {}".format(channel.guild.id))
      if check: await channel.set_permissions(channel.guild.get_role(int(check['role_id'])), view_channel=False, reason="overwriting permissions for jail role")

  @commands.command(description="disable the moderation features in your server", help="moderation")
  @Perms.get_perms("administrator")
  async def unsetmod(self, ctx: commands.Context): 
   check = await self.bot.db.fetchrow("SELECT * FROM mod WHERE guild_id = $1", ctx.guild.id)
   if not check: return await ctx.send_warning( "Moderation is **not** enabled in this server") 
   view = ClearMod(ctx)
   view.message = await ctx.reply(view=view, embed=discord.Embed(color=self.bot.color, description=f"{ctx.author.mention} Are you sure you want to disable moderation?")) 

  @commands.command(description="enable the moderation features in your server", help="moderation")
  @Perms.get_perms("administrator")
  async def setmod(self, ctx: commands.Context): 
   check = await self.bot.db.fetchrow("SELECT * FROM mod WHERE guild_id = $1", ctx.guild.id)
   if check: return await ctx.send_warning( "Moderation is **already** enabled in this server")
   await ctx.typing()
   role = await ctx.guild.create_role(name="yuki-jail")
   for channel in ctx.guild.channels: await channel.set_permissions(role, view_channel=False)
   overwrite = {role: discord.PermissionOverwrite(view_channel=True), ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)}
   over = {ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)}
   category = await ctx.guild.create_category(name="yuki mod", overwrites=over)
   text = await ctx.guild.create_text_channel(name="mod-logs", overwrites=over, category=category)
   jai = await ctx.guild.create_text_channel(name="jail", overwrites=overwrite, category=category)
   await self.bot.db.execute("INSERT INTO mod VALUES ($1,$2,$3,$4)", ctx.guild.id, text.id, jai.id, role.id)
   await self.bot.db.execute("INSERT INTO cases VALUES ($1,$2)", ctx.guild.id, 0)
   return await ctx.send_success("Enabled **moderation** for this server") 

  @commands.command(description="clone a channel", help="moderation", brief="server owner")
  @commands.has_permissions(administrator=True)
  async def nuke(self, ctx: commands.Context): 
        embed = discord.Embed(color=self.bot.color, description=f"Do you want to **nuke** this channel?")
        yes = discord.ui.Button(emoji=self.bot.yes)
        no = discord.ui.Button(emoji=self.bot.no)

        async def yes_callback(interaction: discord.Interaction): 
            if not interaction.user.guild_permissions.administrator:
                return await self.bot.ext.send_warning(interaction, "You need **Administrator** permission to do this", ephemeral=True)

            c = await interaction.channel.clone()
            await c.edit(position=ctx.channel.position)
            await ctx.channel.delete()
            await c.send('first')

            welcome = await self.bot.db.fetchrow("SELECT * FROM welcome WHERE channel_id = $1", ctx.channel.id)
            autopfp = await self.bot.db.fetchrow("SELECT * FROM autopfp WHERE channel_id = $1", ctx.channel.id)
            if welcome or autopfp:
                msg_parts = []
                if welcome: msg_parts.append("welcome")
                if autopfp: msg_parts.append("autopfp")
                msg_text = ", ".join(msg_parts)
                embed = discord.Embed(color=self.bot.color, description=f"Reconfigured {msg_text} channel")
                await c.send(embed=embed)
                if welcome: await self.bot.db.execute("UPDATE welcome SET channel_id = $1 WHERE channel_id = $2", c.id, ctx.channel.id)
                if autopfp: await self.bot.db.execute("UPDATE autopfp SET channel_id = $1 WHERE channel_id = $2", c.id, ctx.channel.id)

        async def no_callback(interaction: discord.Interaction): 
            if not interaction.user.guild_permissions.administrator:
                return await self.bot.ext.send_warning(interaction, "You need **Administrator** permission to do this", ephemeral=True)
            await interaction.response.edit_message(embed=discord.Embed(color=self.bot.color, description="aborting action"), view=None)

        yes.callback = yes_callback
        no.callback = no_callback
        view = discord.ui.View()
        view.add_item(yes)
        view.add_item(no)
        await ctx.reply(embed=embed, view=view)
  
  @commands.hybrid_command(description="restore member's roles", brief="manage roles", usage="[member]", help="moderation")
  @Perms.get_perms("manage_roles")
  @Mod.is_mod_configured()
  async def restore(self, ctx: commands.Context, *, member: discord.Member):    
    async with ctx.message.channel.typing():
      result = await self.bot.db.fetchrow(f"SELECT * FROM restore WHERE user_id = {member.id} AND guild_id = {ctx.guild.id}")         
      if result is None: return await ctx.send_warning(f"Unable to find saved roles for **{member}**")
      to_dump = json.loads(result['roles'])
      roles = [ctx.guild.get_role(r) for r in to_dump if ctx.guild.get_role(r) is not None]
      succeed = ', '.join([f"{r.mention}" for r in roles if r.is_assignable()])
      failed = ', '.join([f"<@&{r.id}>" for r in roles if not r.is_assignable()])
      await member.edit(roles=[r for r in roles if r.position < ctx.guild.get_member(self.bot.user.id).top_role.position and r != ctx.guild.premium_subscriber_role and r != '@everyone'])
      await self.bot.db.execute(f"DELETE FROM restore WHERE user_id = {member.id} AND guild_id = {ctx.guild.id}")
      embed = discord.Embed(color=self.bot.color, title="roles restored", description=f"target: **{member}**")
      embed.set_thumbnail(url=member.display_avatar.url)
      embed.add_field(name="added", value='none' if succeed == ', ' else succeed or "none", inline=False)
      embed.add_field(name="failed", value='none' if failed == ', ' else failed or "none", inline=False)
      return await ctx.reply(embed=embed)
  
  @commands.hybrid_command(aliases=["setnick", "nick"], description="change an user's nickname", usage="[member] <nickname>", help="moderation")
  @Perms.get_perms("manage_nicknames")
  @Mod.is_mod_configured()
  async def nickname(self, ctx, member: NoStaff, *, nick: str=None):
    if nick == None or nick.lower() == "none": return await ctx.send_success(f"Cleared **{member.name}'s** nickname")
    await member.edit(nick=nick)
    return await ctx.send_success(f"Changed **{member.name}'s** nickname to **{nick}**")    

  @commands.command(description="kick members from your server", help="moderation", brief="kick members", usage="[member] <reason>")
  @Perms.get_perms("kick_members")
  @Mod.is_mod_configured()
  async def kick(self, ctx: commands.Context, member: NoStaff, *, reason: str="No reason provided"):
    await ctx.guild.kick(user=member, reason=reason + " | {}".format(ctx.author))
    await ModConfig.send_dm(ctx, member, "kicked", reason)
    await ModConfig.sendlogs(self.bot, "kick", ctx.author, member, reason + " | " + str(ctx.author))
    if not await InvokeClass.invoke_send(ctx, member, reason): await ctx.send_success(f"**{member}** has been kicked | {reason}")

  @commands.hybrid_command(description="ban members from your server", help="moderation", brief="ban members", usage="[member] <reason>")
  @Perms.get_perms("ban_members")
  @Mod.is_mod_configured()
  async def ban(self, ctx: commands.Context, member: NoStaff, *, reason: str="No reason provided"):
   await ctx.guild.ban(user=member, reason=reason + " | {}".format(ctx.author))
   await ModConfig.send_dm(ctx, member, "banned", reason)
   await ModConfig.sendlogs(self.bot, "ban", ctx.author, member, reason + " | " + str(ctx.author))
   if not await InvokeClass.invoke_send(ctx, member, reason): await ctx.send_success(f"**{member}** has been banned | {reason}")
  
  @commands.hybrid_command(description="mute members in your server", help="moderation", brief="moderate members", usage="[member] [time] <reason>", aliases=["timeout"])
  @Perms.get_perms("moderate_members")
  @Mod.is_mod_configured()
  async def mute(self, ctx: commands.Context, member: NoStaff, time: str="60s", *, reason="No reason provided"): 
     tim = humanfriendly.parse_timespan(time)
     until = discord.utils.utcnow() + datetime.timedelta(seconds=tim)
     await member.timeout(until, reason=reason + " | {}".format(ctx.author))
     if not await InvokeClass.invoke_send(ctx, member, reason): await ctx.send_success(f"**{member}** has been muted for {humanfriendly.format_timespan(tim)} | {reason}")
     await ModConfig.sendlogs(self.bot, "mute", ctx.author, member, reason + " | " + humanfriendly.format_timespan(tim))
     await ModConfig.send_dm(ctx, member, "muted", reason + " | " + humanfriendly.format_timespan(tim))
  
  @commands.command(description="unban an user", help="moderation", usage="[member] [reason]")
  @Perms.get_perms("ban_members")
  @Mod.is_mod_configured()
  async def unban(self, ctx: commands.Context, member: discord.User, *, reason: str="No reason provided"):
    try:
     await ctx.guild.unban(user=member, reason=reason + f" | unbanned by {ctx.author}")
     if not await InvokeClass.invoke_send(ctx, member, reason): await ctx.send_success(f"**{member}** has been unbanned")
    except discord.NotFound: return await ctx.send_warning( f"Couldn't find ban for **{member}**") 
  
  @commands.command(description="ban an user then immediately unban them", help="moderation", usage="[member] [reason]")
  @Perms.get_perms("ban_members")
  @Mod.is_mod_configured()
  async def softban(self, ctx: commands.Context, member: NoStaff, *, reason: str="No reason provided"): 
    await member.ban(delete_message_days=7, reason=reason + f" | banned by {ctx.author}")
    await ctx.guild.unban(user=member)
    await ctx.send_success(f"Softbanned **{member}**")

  @commands.hybrid_command(description="unmute a member in your server", help="moderation", brief="moderate members", usage="[member] <reason>", aliases=["untimeout"])
  @Perms.get_perms("moderate_members")
  @Mod.is_mod_configured()
  async def unmute(self, ctx: commands.Context, member: NoStaff, * , reason: str="No reason provided"): 
    if not member.is_timed_out(): return await ctx.send_warning( f"**{member}** is not muted")
    await member.edit(timed_out_until=None, reason=reason + " | {}".format(ctx.author))
    if not await InvokeClass.invoke_send(ctx, member, reason): await ctx.send_success(f"**{member}** has been unmuted")
    await ModConfig.sendlogs(self.bot, "unmute", ctx.author, member, reason)
  
  @commands.command(aliases=['vcmute'], description="mute a member in a voice channel", brief="moderate members", usage="[member]", help="moderation")
  @Perms.get_perms("moderate_members")  
  async def voicemute(self, ctx: commands.Context, *, member: NoStaff): 
      if not member.voice.channel: return await ctx.send_warning( f"**{member}** is **not** in a voice channel")
      if member.voice.self_mute: return await ctx.send_warning( f"**{member}** is **already** voice muted")
      await member.edit(mute=True, reason=f"Voice muted by {ctx.author}")
      return await ctx.send_success(f"Voice muted **{member}**")
 
  @commands.command(aliases=['vcunmute'], description="unmute a member in a voice channel", brief="moderate members", usage="[member]", help="moderation")
  @Perms.get_perms("moderate_members")  
  async def voiceunmute(self, ctx: commands.Context, *, member: NoStaff): 
      if not member.voice.channel: return await ctx.send_warning( f"**{member}** is **not** in a voice channel")
      if not member.voice.self_mute: return await ctx.send_warning( f"**{member}** is **not** voice muted")
      await member.edit(mute=True, reason=f"Voice muted by {ctx.author}")
      return await ctx.send_success(f"Voice muted **{member}**")

  @commands.command(description="purges an amount of messages sent by you", help="donor", usage="[amount]")
  async def selfpurge(self, ctx: commands.Context, amount: int):
     mes = [] 
     async for message in ctx.channel.history(): 
      if (len(mes) == amount+1): break 
      if message.author == ctx.author: mes.append(message)
           
     await ctx.channel.delete_messages(mes)
  
  @commands.group(name="clear", invoke_without_command=True)
  async def mata_clear(self, ctx): 
    return await ctx.create_pages()
  
  @mata_clear.command(help="moderation", description="clear messages that contain a certain word", usage="[word]", brief="manage messages")
  async def contains(self, ctx: commands.Context, *, word: str): 
   messages = [message async for message in ctx.channel.history(limit=300) if word in message.content]
   if len(messages) == 0: return await ctx.send_warning(f"No messages containing **{word}** in this channel")
   await ctx.channel.delete_messages(messages)

  @commands.command(aliases=['p'], description="bulk delete messages", help="moderation", brief="manage messages", usage="[messages]")  
  @Perms.get_perms("manage_messages")  
  async def purge(self, ctx: commands.Context, amount: int, *, member: NoStaff=None):
   if member is None: 
    await ctx.channel.purge(limit=amount+1, bulk=True, reason=f"purge invoked by {ctx.author}")
    return await ctx.send(f"purged `{amount}` messages", delete_after=2) 
   messages = []
   async for m in ctx.channel.history(): 
    if m.author.id == member.id: messages.append(m)
    if len(messages) == amount: break 
   messages.append(ctx.message)
   await ctx.channel.delete_messages(messages)
   return await ctx.send(f"purged `{amount}` messages sent by `{member}`", delete_after=2)
  
  @commands.command(description="Bulk delete messages sent by bots or starting with the bot prefix",help="moderation",usage="[amount]",aliases=["bc","botclear"])
  @Perms.get_perms("manage_messages")
  async def botpurge(self,ctx:commands.Context,amount:int=50):
      import datetime
      prefix=await self.bot.get_prefix(ctx.message)
      if isinstance(prefix,list):prefix=prefix[0]
      def is_bot_or_prefix(m):return m.author.bot or m.content.startswith(prefix)
      
      # Discord only allows bulk delete for messages under 14 days old
      fourteen_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
      
      deleted=0
      last=None
      while deleted<amount:
          fetch_limit=min(100,amount-deleted)
          messages=[]
          async for m in ctx.channel.history(limit=fetch_limit,before=last):
              if is_bot_or_prefix(m):
                  # Only include messages that are less than 14 days old
                  if m.created_at > fourteen_days_ago:
                      messages.append(m)
          if not messages:break
          
          # Split messages into batches for bulk delete (max 100 per batch)
          for i in range(0, len(messages), 100):
              batch = messages[i:i+100]
              try:
                  await ctx.channel.delete_messages(batch)
                  deleted+=len(batch)
              except discord.HTTPException as e:
                  # If bulk delete fails (e.g., message too old), delete individually
                  for msg in batch:
                      try:
                          await msg.delete()
                          deleted+=1
                      except:
                          pass
          
          if messages:
              last=messages[-1]
          else:
              break
      
      if ctx.message:
          try:await ctx.message.delete()
          except:pass
      
      if deleted > 0:
          await ctx.send(embed=discord.Embed(description=f"Deleted {deleted} bot/command message(s)"), delete_after=3)

  @commands.command(description="Delete all messages up to and including a specific message", help="moderation", brief="manage messages", usage="[message_link]")
  @Perms.get_perms("manage_messages")
  async def purgeupto(self, ctx: commands.Context, message_link: str):
      import datetime
      
      # Parse message link - try to get message ID directly first, then try link parsing
      target_message = None
      try:
          # Try parsing as message ID first
          message_id = int(message_link)
          target_message = await ctx.channel.fetch_message(message_id)
      except (ValueError, discord.NotFound):
          # Try parsing as message link
          try:
              target_message = await self.bot.ext.link_to_message(message_link)
          except Exception as e:
              await ctx.send_warning(f"Could not find message. Make sure the link is valid and the message is in this channel.")
              return
      
      if not target_message:
          await ctx.send_warning("Could not find the target message.")
          return
      
      # Verify message is in the same channel
      if target_message.channel.id != ctx.channel.id:
          await ctx.send_warning("The target message must be in the same channel as this command.")
          return
      
      # Verify target message is older than the command message (we want to delete up to it)
      if target_message.id >= ctx.message.id:
          await ctx.send_warning("The target message must be older than this command message.")
          return
      
      # Discord only allows bulk delete for messages under 14 days old
      fourteen_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
      
      # Collect all messages from current message up to and including target message
      messages_to_delete = [ctx.message]  # Include the command message
      messages_to_delete.append(target_message)  # Include the target message
      
      # Fetch messages between the command message and target message
      async for message in ctx.channel.history(after=target_message, before=ctx.message):
          # Only include messages that are less than 14 days old for bulk delete
          if message.created_at > fourteen_days_ago:
              messages_to_delete.append(message)
      
      # Sort by ID to ensure proper order (oldest first)
      messages_to_delete.sort(key=lambda m: m.id)
      
      if len(messages_to_delete) == 0:
          await ctx.send_warning("No messages to delete.")
          return
      
      deleted = 0
      
      # Split into batches of 100 (Discord's bulk delete limit)
      for i in range(0, len(messages_to_delete), 100):
          batch = messages_to_delete[i:i+100]
          try:
              await ctx.channel.delete_messages(batch)
              deleted += len(batch)
          except discord.HTTPException as e:
              # If bulk delete fails (e.g., message too old), delete individually
              for msg in batch:
                  try:
                      await msg.delete()
                      deleted += 1
                  except:
                      pass
      
      if deleted > 0:
          await ctx.send(embed=discord.Embed(description=f"Deleted {deleted} message(s) up to the target message."), delete_after=3)
      else:
          await ctx.send_warning("No messages were deleted.")

   

  @commands.command(help="removes all staff roles from a member", description="moderation", usage="[member] [reason]")
  @Perms.get_perms("administrator")
  @Mod.is_mod_configured()
  async def strip(self, ctx: commands.Context, member: NoStaff, *, reason: str='No reason provided'):
     await ctx.channel.typing()  
     await member.edit(roles=[role for role in member.roles if not role.is_assignable() or not self.bot.is_dangerous(role) or role.is_premium_subscriber()], reason=reason + " | Moderator: {}".format(ctx.author)) 
     await ctx.send_success(f"Removed **{member}'s** roles")       
     await ModConfig.sendlogs(self.bot, "strip", ctx.author, member, reason)

  @commands.group(invoke_without_command=True)
  @Perms.get_perms("manage_messages")
  @Mod.is_mod_configured()
  async def warn(self, ctx: commands.Context, member: NoStaff=None, *, reason: str="No reason provided"):
       if member is None: return await ctx.create_pages() 
       date = datetime.datetime.now()
       await self.bot.db.execute("INSERT INTO warns VALUES ($1,$2,$3,$4,$5)", ctx.guild.id, member.id, ctx.author.id, f"{date.day}/{f'0{date.month}' if date.month < 10 else date.month}/{str(date.year)[-2:]} at {datetime.datetime.strptime(f'{date.hour}:{date.minute}', '%H:%M').strftime('%I:%M %p')}", reason)
       if not await InvokeClass.invoke_send(ctx, member, reason): await ctx.send_success(f"Warned **{member}** | {reason}")
       await ModConfig.sendlogs(self.bot, "warn", ctx.author, member, reason)
       await ModConfig.send_dm(ctx, member, "warned", reason)

  @warn.command(description="clear all warns from an user", help="moderation", usage="[member]", brief="manage messages")
  @Perms.get_perms("manage_messages")
  @Mod.is_mod_configured()
  async def clear(self, ctx: commands.Context, *, member: NoStaff): 
      check = await self.bot.db.fetch("SELECT * FROM warns WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id)   
      if len(check) == 0: return await ctx.send_warning( "this user has no warnings".capitalize())
      await self.bot.db.execute("DELETE FROM warns WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id)
      await ctx.send_success(f"Removed **{member.name}'s** warns")

  @warn.command(name="list", description="shows all warns of an user", help="moderation", usage="[member]")
  @Mod.is_mod_configured()
  async def list(self, ctx: commands.Context, *, member: discord.Member): 
      check = await self.bot.db.fetch("SELECT * FROM warns WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id)  
      if len(check) == 0: return await ctx.send_warning( "this user has no warnings".capitalize())
      i=0
      k=1
      l=0
      mes = ""
      number = []
      messages = []
      for result in check:
              mes = f"{mes}`{k}` {result['time']} by **{await self.bot.fetch_user(result['author_id'])}** - {result['reason']}\n"
              k+=1
              l+=1
              if l == 10:
               messages.append(mes)
               number.append(discord.Embed(color=self.bot.color, title=f"warns ({len(check)})", description=messages[i]))
               i+=1
               mes = ""
               l=0
    
      messages.append(mes)
      embed = discord.Embed(color=self.bot.color, title=f"warns ({len(check)})", description=messages[i]).set_footer(text="All times are GMT")
      number.append(embed)
      await ctx.paginator(number)

  @commands.command(description="shows all warns of an user", help="moderation", usage="[member]")
  @Mod.is_mod_configured()
  async def warns(self, ctx: commands.Context, *, member: discord.Member): 
    return await ctx.invoke(self.bot.get_command('warn list'), member=member)

  @commands.command(description="jail a member", usage="[member]", help="moderation", brief="manage channels")
  @Perms.get_perms("manage_channels")
  @Mod.is_mod_configured()
  async def jail(self, ctx: commands.Context, member: NoStaff, *, reason: str="No reason provided"):
      check = await self.bot.db.fetchrow("SELECT * FROM jail WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id)      
      if check: return await ctx.send_warning( f"**{member}** is already jailed")     
      if reason == None: reason = "No reason provided"
      roles = [r.id for r in member.roles if r.name != "@everyone" and r.is_assignable()]
      sql_as_text = json.dumps(roles)
      await self.bot.db.execute("INSERT INTO jail VALUES ($1,$2,$3)", ctx.guild.id, member.id, sql_as_text)   
      chec = await self.bot.db.fetchrow("SELECT * FROM mod WHERE guild_id = $1", ctx.guild.id)   
      roleid = chec["role_id"]
      try:
       jail = ctx.guild.get_role(roleid)
       new = [r for r in member.roles if not r.is_assignable()]
       new.append(jail) 
       if not await InvokeClass.invoke_send(ctx, member, reason): await member.edit(roles=new, reason=f"jailed by {ctx.author} - {reason}")
       await ctx.send_success(f"**{member}** got jailed - {reason}")
       await ModConfig.sendlogs(self.bot, "jail", ctx.author, member, reason)
       await ModConfig.send_dm(ctx, member, "jailed", reason)
       c = ctx.guild.get_channel(int(chec['jail_id']))
       if c: await c.send(f"{member.mention}, you have been jailed! Wait for a staff member to unjail you and check dm's if you have received one!") 
      except: return await ctx.send_error( f"There was a problem jailing **{member}**")

  @commands.command(description="unjail a member", usage="[member] [reason]", help="moderation", brief="manage channels")
  @Perms.get_perms("manage_channels")
  @Mod.is_mod_configured()
  async def unjail(self, ctx: commands.Context, member: discord.Member, *, reason: str="No reason provided"):   
      check = await self.bot.db.fetchrow("SELECT * FROM jail WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id)      
      if not check: return await ctx.send_warning( f"**{member}** is not jailed")     
      sq = check['roles']
      roles = json.loads(sq)
      try: await member.edit(roles=[ctx.guild.get_role(role) for role in roles if ctx.guild.get_role(role)], reason=f"unjailed by {ctx.author}")
      except: pass
      await self.bot.db.execute("DELETE FROM jail WHERE user_id = {} AND guild_id = {}".format(member.id, ctx.guild.id))
      if not await InvokeClass.invoke_send(ctx, member, reason): await ctx.send_success(f"Unjailed **{member}**")
      await ModConfig.sendlogs(self.bot, "unjail", ctx.author, member, reason)
  
  @commands.command(aliases=["sm"], description="add slowmode to a channel", help="moderation", usage="[seconds] <channel>", brief="manage channelss")  
  @Perms.get_perms("manage_channels")
  @Mod.is_mod_configured()
  async def slowmode(self, ctx: commands.Context, seconds: str, channel: discord.TextChannel=None):
    chan = channel or ctx.channel
    tim = humanfriendly.parse_timespan(seconds)
    await chan.edit(slowmode_delay=tim, reason="slowmode invoked by {}".format(ctx.author))
    return await ctx.send_success(f"Slowmode for {channel.mention} set to **{humanfriendly.format_timespan(tim)}**")

  @commands.command(description="lock a channel", help="moderation", usage="<channel>", brief="manage channels")
  @Perms.get_perms("manage_channels")
  @Mod.is_mod_configured()
  async def lock(self, ctx: commands.Context, channel : discord.TextChannel=None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    return await ctx.send_success(f"Locked {channel.mention}")

  @commands.command(description="unlock a channel", help="moderation", usage="<channel>", brief="manage channels")
  @Perms.get_perms("manage_channels")
  @Mod.is_mod_configured()
  async def unlock(self, ctx: commands.Context, channel : discord.TextChannel=None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    return await ctx.send_success(f"Unlocked {channel.mention}")       
    
  @commands.group(invoke_without_command=True, description="manage roles in your server", help="moderation", aliases=['r'])
  @Perms.get_perms("manage_roles")
  async def role(self, ctx: commands.Context, user: discord.Member=None, *, role : GoodRole=None):  
    if role == None or user == None: return await ctx.create_pages()
    if role in user.roles:
      await user.remove_roles(role)
      return await ctx.send_success(f"Removed {role.mention} from **{user.name}**")
    else: 
      await user.add_roles(role)
      return await ctx.send_success(f"Added {role.mention} to **{user.name}**")

  @role.command(description="add a role to an user", help="moderation", usage="[user] [role]", name="add", brief="manage roles")
  @Perms.get_perms("manage_roles")
  async def role_add(self, ctx: commands.Context, user: discord.Member, *, role: GoodRole):
    if role in user.roles: return await ctx.send_error( f"**{user}** has this role already") 
    await user.add_roles(role)
    return await ctx.send_success(f"Added {role.mention} to **{user.name}**")
   
  @role.command(name="remove", help="moderation", brief="manage roles", description="remove a role from a member")
  @Perms.get_perms("manage_roles")
  async def role_remove(self, ctx: commands.Context, user: discord.Member, *, role: GoodRole):
    if not role in user.roles: return await ctx.send_error( f"**{user}** doesn't this role")
    await user.remove_roles(role)
    return await ctx.send_success(f"Removed {role.mention} from **{user.name}**")   

  @role.command(description="create a role", help="moderation", usage="[name]", brief="manage roles")
  @Perms.get_perms("manage_roles")
  async def create(self, ctx: commands.Context, *, name: str): 
    role = await ctx.guild.create_role(name=name, reason=f"changed role name by {ctx.author}")
    return await ctx.send_success(f"Created role {role.mention}") 
   
  @role.command(description="delete a role", help="moderation", usage="[role]", brief="manage roles")
  @Perms.get_perms("manage_roles")
  async def delete(self, ctx: commands.Context, *, role: GoodRole): 
      await role.delete()
      return await ctx.send_success("Deleted the role") 
   
  @role.group(invoke_without_command=True, help="moderation", description="edit a role")
  async def edit(self, ctx: commands.Context): 
   return await ctx.create_pages()
   
  @edit.command(description="make a role visible separately.. or not", brief="manage roles", help="moderation", usage="[role] [bool <true or false>]")
  @Perms.get_perms("manage_roles")
  async def hoist(self, ctx: commands.Context, role: GoodRole, state: str): 
     if not state.lower() in ["true", "false"]: return await ctx.send_error( f"**{state}** can be only **true** or **false**")
     await role.edit(hoist=bool(state.lower() == "true"))
     return await ctx.send_success(f"{f'The role is now hoisted' if role.hoist is True else 'The role is not hoisted anymore'}")

  @edit.command(aliases=["pos"], description="change a role's position", help="moderation", usage="[role] [base role]", brief="manage roles")
  @Perms.get_perms("manage_roles")
  async def position(self, ctx: commands.Context, role: GoodRole, position: GoodRole):
     await role.edit(position=position.position)
     return await ctx.send_success(f"Role position changed to `{position.position}`")

  @edit.command(description="change a role's icon", brief="manage roles", help="moderation", usage="[role] <emoji>")
  @Perms.get_perms("manage_roles")
  async def icon(self, ctx: commands.Context, role: GoodRole, emoji: Union[discord.PartialEmoji, str]):      
      if isinstance(emoji, discord.PartialEmoji): 
       by = await emoji.read()
       await role.edit(display_icon=by)      
      elif isinstance(emoji, str): await role.edit(display_icon=str(emoji))
      return await ctx.send_success("Changed role icon")
  
  @edit.command(brief="manage roles", description="change a role's name", help="moderation", usage="[role] [name]")
  @Perms.get_perms("manage_roles")
  async def name(self, ctx: commands.Context, role: GoodRole, *, name: str): 
     await role.edit(name=name, reason=f"role edited by {ctx.author}")
     return await ctx.send_success(f"Edited the role's name in **{name}**")

  @edit.command(description="change a role's color", help="moderation", usage="[role] [color]")
  @Perms.get_perms("manage_roles")
  async def color(self, ctx: commands.Context, role: GoodRole, *, color: str):  
    try: 
      color = color.replace("#", "")
      await role.edit(color=int(color, 16), reason=f"role edited by {ctx.author}")
      return await ctx.reply(embed=discord.Embed(color=role.color, description=f"{self.bot.yes} {ctx.author.mention}: Changed role's color"))
    except: return await ctx.send_error( "Unable to change the role's color")  
  
  @role.group(invoke_without_command=True, name="humans", description="mass add or remove roles from members", help="moderation")  
  async def rolehumans(self, ctx: commands.Context):
    return await ctx.create_pages()
  
  @rolehumans.command(name="remove", description="remove a role from all members in this server", help="moderation", usage='[role]', brief="manage_roles")
  @Perms.get_perms("manage_roles")
  async def rolehumansremove(self, ctx: commands.Context, *, role: GoodRole):
      embed = discord.Embed(color=self.bot.color, description=f"{ctx.author.mention} Removing {role.mention} from all humans....")
      message = await ctx.reply(embed=embed)
      try:
         for member in [m for m in ctx.guild.members if not m.bot]: 
            if not role in member.roles: continue
            await member.remove_roles(role)

         await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.yes} {ctx.author.mention}: Removed {role.mention} from all humans"))
      except Exception: await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.no} {ctx.author.mention}: Unable to remove {role.mention} from all humans"))  
  
  @rolehumans.command(name="add", description="add a role to all humans in this server", help="moderation", usage='[role]', brief="manage_roles")  
  @Perms.get_perms("manage_roles")
  async def rolehumansadd(self, ctx: commands.Context, *, role: GoodRole):  
    embed = discord.Embed(color=self.bot.color, description=f"{ctx.author.mention}: Adding {role.mention} to all humans....")
    message = await ctx.reply(embed=embed)
    try:
     for member in [m for m in ctx.guild.members if not m.bot]: 
       if role in member.roles: continue
       await member.add_roles(role)

     await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.yes} {ctx.author.mention}: Added {role.mention} to all humans"))
    except Exception: await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.no} {ctx.author.mention}: Unable to add {role.mention} to all humans")) 

  @role.group(invoke_without_command=True, name="bots", description="mass add or remove roles from members", help="moderation")  
  async def rolebots(self, ctx: commands.Context):
    return await ctx.create_pages()
  
  @rolebots.command(name="remove", description="remove a role from all bots in this server", help="moderation", usage='[role]', brief="manage_roles")
  @Perms.get_perms("manage_roles")
  async def rolebotsremove(self, ctx: commands.Context, *, role: GoodRole):
      embed = discord.Embed(color=self.bot.color, description=f"{ctx.author.mention} Removing {role.mention} from all bots....")
      message = await ctx.reply(embed=embed)
      try:
         for member in [m for m in ctx.guild.members if m.bot]: 
            if not role in member.roles: continue
            await member.remove_roles(role)

         await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.yes} {ctx.author.mention}: Removed {role.mention} from all bots"))
      except Exception: await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.no} {ctx.author.mention}: Unable to remove {role.mention} from all bots"))  
  
  @rolebots.command(name="add", description="add a role to all bots in this server", help="moderation", usage='[role]', brief="manage_roles")  
  @Perms.get_perms("manage_roles")
  async def rolebotsadd(self, ctx: commands.Context, *, role: GoodRole):  
    embed = discord.Embed(color=self.bot.color, description=f"{ctx.author.mention}: Adding {role.mention} to all bots....")
    message = await ctx.reply(embed=embed)
    try:
     for member in [m for m in ctx.guild.members if m.bot]: 
       if role in member.roles: continue
       await member.add_roles(role)

     await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.yes} {ctx.author.mention}: Added {role.mention} to all bots"))
    except Exception: await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.no} {ctx.author.mention}: Unable to add {role.mention} to all bots"))    

  @role.group(invoke_without_command=True, name="all", description="mass add or remove roles from members", help="moderation")  
  async def roleall(self, ctx: commands.Context):
    return await ctx.create_pages()
  
  @roleall.command(name="remove", description="remove a role from all members in this server", help="moderation", usage='[role]', brief="manage_roles")
  @Perms.get_perms("manage_roles")
  async def roleallremove(self, ctx: commands.Context, *, role: GoodRole):
      embed = discord.Embed(color=self.bot.color, description=f"{ctx.author.mention} Removing {role.mention} from all members....")
      message = await ctx.reply(embed=embed)
      try:
         for member in ctx.guild.members: 
            if not role in member.roles: continue
            await member.remove_roles(role)

         await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.yes} {ctx.author.mention}: Removed {role.mention} from all members"))
      except Exception: await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.no} {ctx.author.mention}: Unable to remove {role.mention} from all members"))  
  
  @roleall.command(name="add", description="add a role to all members in this server", help="moderation", usage='[role]', brief="manage_roles")  
  @Perms.get_perms("manage_roles")
  async def rolealladd(self, ctx: commands.Context, *, role: GoodRole):  
    embed = discord.Embed(color=self.bot.color, description=f"{ctx.author.mention}: Adding {role.mention} to all members....")
    message = await ctx.reply(embed=embed)
    try:
     for member in ctx.guild.members: 
       if role in member.roles: continue
       await member.add_roles(role)

     await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.yes} {ctx.author.mention}: Added {role.mention} to all members"))
    except Exception: await message.edit(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.no} {ctx.author.mention}: Unable to add {role.mention} to all members"))    
  @commands.command(description="hardban | hardunban an user from the server", help="moderation", usage="[user]", brief="ban_members")
  @Perms.get_perms("ban_members")
  async def hardban(self, ctx: commands.Context, *, member: Union[discord.Member, discord.User]): 
    if isinstance(member, discord.Member):
      if member == ctx.message.author: return await ctx.send_warning("You cannot hardban **yourself**")
      if member.id == self.bot.user.id: return await ctx.reply("leave me alone <:angry:1037460375223939112>")
      if await Mod.check_hieracy(ctx, member):   
       che = await self.bot.db.fetchrow("SELECT * FROM hardban WHERE guild_id = {} AND banned = {}".format(ctx.guild.id, member.id))
       if che is not None: return await ctx.send_warning(f"**{member}** has been hardbanned by **{await self.bot.fetch_user(che['author'])}**")
       await ctx.guild.ban(member, reason="hardbanned by {}".format(ctx.author))
       await self.bot.db.execute("INSERT INTO hardban VALUES ($1,$2,$3)", ctx.guild.id, member.id, ctx.author.id)
       await ctx.message.add_reaction("👍🏿")
  
  @commands.command(description="uwuify a person's messages", help="moderation", usage="[member]", brief="administrator")
  @Perms.get_perms("administrator")
  async def uwulock(self, ctx: commands.Context, *, member: NoStaff): 
     if member.bot: return await ctx.send_warning("You can't **uwulock** a bot")
     check = await self.bot.db.fetchrow("SELECT user_id FROM uwulock WHERE user_id = {} AND guild_id = {}".format(member.id, ctx.guild.id))    
     if check is None: await self.bot.db.execute("INSERT INTO uwulock VALUES ($1,$2)", ctx.guild.id, member.id)
     else: await self.bot.db.execute("DELETE FROM uwulock WHERE user_id = {} AND guild_id = {}".format(member.id, ctx.guild.id))    
     return await ctx.message.add_reaction("👍🏿")
  
  @commands.command(description="force nicknames an user", help="", usage="[member] [nickname]\nif none is passed as nickname, the force nickname gets removed", aliases=["locknick", "fn"], brief="manage nicknames")
  @Perms.get_perms("manage_nicknames")
  async def forcenick(self, ctx: commands.Context, member: NoStaff, *, nick: str): 
             if nick.lower() == "none": 
               check = await self.bot.db.fetchrow("SELECT * FROM forcenick WHERE user_id = {} AND guild_id = {}".format(member.id, ctx.guild.id))
               if check is None: return await ctx.send_warning(f"**No** forcenick found for {member}")
               await self.bot.db.execute("DELETE FROM forcenick WHERE user_id = {} AND guild_id = {}".format(member.id, ctx.guild.id))              
               await member.edit(nick=None)
               await ctx.message.add_reaction("👍🏿")
             else: 
               check = await self.bot.db.fetchrow("SELECT * FROM forcenick WHERE user_id = {} AND guild_id = {}".format(member.id, ctx.guild.id))               
               if check is None: await self.bot.db.execute("INSERT INTO forcenick VALUES ($1,$2,$3)", ctx.guild.id, member.id, nick)
               else: await self.bot.db.execute("UPDATE forcenick SET nickname = '{}' WHERE user_id = {} AND guild_id = {}".format(nick, member.id, ctx.guild.id))  
               await member.edit(nick=nick)
               await ctx.message.add_reaction("👍🏿")

  @commands.command(description="revoke the hardban from an user", help="moderation", usage="[user]", brief="ban_members")
  @Perms.get_perms("ban_members")
  async def hardunban(self, ctx: commands.Context, *, member: discord.User):     
      che = await self.bot.db.fetchrow("SELECT * FROM hardban WHERE guild_id = {} AND banned = {}".format(ctx.guild.id, member.id))      
      if che is None: return await ctx.send_warning(f"{member} is **not** hardbanned") 
      await self.bot.db.execute("DELETE FROM hardban WHERE guild_id = {} AND banned = {}".format(ctx.guild.id, member.id))
      await ctx.guild.unban(member, reason="unhardbanned by {}".format(ctx.author.mention)) 
      await ctx.message.add_reaction("👍🏿")

  @commands.group(invoke_without_command=True, description="manage role restrictions", help="moderation")
  async def restrict(self, ctx: commands.Context):
      await ctx.create_pages()

  @restrict.command(name="add", description="restrict a role from accessing channels", help="moderation", brief="manage guild", usage="[role] [channel]")
  @Perms.get_perms("manage_guild")
  async def restrict_add(self, ctx: commands.Context, role: discord.Role, channel: Union[discord.TextChannel, discord.VoiceChannel]):
      if role >= ctx.guild.me.top_role:
          return await ctx.send_warning("I cannot manage this role")
      if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
          return await ctx.send_warning("You cannot manage this role")
      
      check = await self.bot.db.fetchrow(
          "SELECT * FROM restrict_role WHERE guild_id = $1 AND role_id = $2 AND channel_id = $3",
          ctx.guild.id, role.id, channel.id
      )
      if check:
          return await ctx.send_warning(f"{role.mention} is already restricted from {channel.mention}")
      
      # Apply channel permission overwrite
      try:
          await channel.set_permissions(
              role, 
              view_channel=False,
              read_messages=False,
              send_messages=False,
              connect=False,
              reason=f"Role restricted by {ctx.author}"
          )
      except discord.Forbidden:
          return await ctx.send_warning("I don't have permission to modify that channel")
      
      await self.bot.db.execute(
          "INSERT INTO restrict_role VALUES ($1, $2, $3)",
          ctx.guild.id, role.id, channel.id
      )
      return await ctx.send_success(f"Restricted {role.mention} from accessing {channel.mention}")

  @restrict.command(name="remove", description="remove role restriction from a channel", help="moderation", brief="manage guild", usage="[role] [channel]")
  @Perms.get_perms("manage_guild")
  async def restrict_remove(self, ctx: commands.Context, role: discord.Role, channel: Union[discord.TextChannel, discord.VoiceChannel]):
      check = await self.bot.db.fetchrow(
          "SELECT * FROM restrict_role WHERE guild_id = $1 AND role_id = $2 AND channel_id = $3",
          ctx.guild.id, role.id, channel.id
      )
      if not check:
          return await ctx.send_warning(f"{role.mention} is not restricted from {channel.mention}")
      
      # Remove channel permission overwrite
      try:
          await channel.set_permissions(role, overwrite=None, reason=f"Role unrestricted by {ctx.author}")
      except discord.Forbidden:
          return await ctx.send_warning("I don't have permission to modify that channel")
      
      await self.bot.db.execute(
          "DELETE FROM restrict_role WHERE guild_id = $1 AND role_id = $2 AND channel_id = $3",
          ctx.guild.id, role.id, channel.id
      )
      return await ctx.send_success(f"Removed restriction for {role.mention} from {channel.mention}")

  @restrict.command(name="list", description="view all role restrictions", help="moderation")
  async def restrict_list(self, ctx: commands.Context):
      results = await self.bot.db.fetch(
          "SELECT * FROM restrict_role WHERE guild_id = $1",
          ctx.guild.id
      )
      if len(results) == 0:
          return await ctx.send_warning("No role restrictions found")
      
      i = 0
      k = 1
      l = 0
      mes = ""
      number = []
      messages = []
      
      for result in results:
          role = ctx.guild.get_role(result['role_id'])
          channel = ctx.guild.get_channel(result['channel_id'])
          if role and channel:
              mes = f"{mes}`{k}` {role.mention} → {channel.mention}\n"
              k += 1
              l += 1
          if l == 10:
              messages.append(mes)
              number.append(discord.Embed(
                  color=self.bot.color,
                  title=f"Role Restrictions ({len(results)})",
                  description=messages[i]
              ))
              i += 1
              mes = ""
              l = 0
      
      messages.append(mes)
      number.append(discord.Embed(
          color=self.bot.color,
          title=f"Role Restrictions ({len(results)})",
          description=messages[i]
      ))
      await ctx.paginator(number)

  @commands.group(invoke_without_command=True, description="disable or enable commands globally", help="moderation", aliases=['disablecmd'])
  async def disablecommand(self, ctx: commands.Context):
      await ctx.create_pages()

  @disablecommand.command(name="add", description="disable a command globally in this server", help="moderation", brief="manage guild", usage="[command]")
  @Perms.get_perms("manage_guild")
  async def disablecommand_add(self, ctx: commands.Context, *, command: str):
      cmd = self.bot.get_command(command)
      if not cmd:
          return await ctx.send_warning(f"Command **{command}** not found")
      
      # Prevent disabling critical commands
      if cmd.name in ['help', 'disablecommand', 'enablecommand']:
          return await ctx.send_warning("You cannot disable this command")
      
      check = await self.bot.db.fetchrow(
          "SELECT * FROM disabled_commands WHERE guild_id = $1 AND command = $2",
          ctx.guild.id, cmd.name
      )
      if check:
          return await ctx.send_warning(f"Command **{cmd.name}** is already disabled")
      
      await self.bot.db.execute(
          "INSERT INTO disabled_commands VALUES ($1, $2)",
          ctx.guild.id, cmd.name
      )
      # Invalidate cache
      self.bot._disabled_commands_cache.pop(ctx.guild.id, None)
      self.bot._disabled_commands_cache_time.pop(ctx.guild.id, None)
      
      return await ctx.send_success(f"Disabled command **{cmd.name}** in this server")

  @disablecommand.command(name="remove", description="enable a previously disabled command", help="moderation", brief="manage guild", usage="[command]", aliases=['enable'])
  @Perms.get_perms("manage_guild")
  async def disablecommand_remove(self, ctx: commands.Context, *, command: str):
      cmd = self.bot.get_command(command)
      if not cmd:
          return await ctx.send_warning(f"Command **{command}** not found")
      
      check = await self.bot.db.fetchrow(
          "SELECT * FROM disabled_commands WHERE guild_id = $1 AND command = $2",
          ctx.guild.id, cmd.name
      )
      if not check:
          return await ctx.send_warning(f"Command **{cmd.name}** is not disabled")
      
      await self.bot.db.execute(
          "DELETE FROM disabled_commands WHERE guild_id = $1 AND command = $2",
          ctx.guild.id, cmd.name
      )
      # Invalidate cache
      self.bot._disabled_commands_cache.pop(ctx.guild.id, None)
      self.bot._disabled_commands_cache_time.pop(ctx.guild.id, None)
      
      return await ctx.send_success(f"Enabled command **{cmd.name}** in this server")

  @disablecommand.command(name="list", description="view all disabled commands", help="moderation")
  async def disablecommand_list(self, ctx: commands.Context):
      results = await self.bot.db.fetch(
          "SELECT command FROM disabled_commands WHERE guild_id = $1",
          ctx.guild.id
      )
      if len(results) == 0:
          return await ctx.send_warning("No commands are disabled")
      
      commands_list = [f"`{i+1}` {result['command']}" for i, result in enumerate(results)]
      embed = discord.Embed(
          color=self.bot.color,
          title=f"Disabled Commands ({len(results)})",
          description="\n".join(commands_list)
      )
      await ctx.reply(embed=embed)

async def setup(bot: commands.Bot): 
    await bot.add_cog(Moderation(bot))      
