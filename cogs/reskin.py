import discord
from discord.ext import commands

class reskin(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    async def get_webhook(self, channel, name):
        webhooks = await channel.webhooks()
        for webhook in webhooks:
            if webhook.name == name:
                return webhook
        return None

    # Webhook creation disabled - no longer auto-creating webhooks
    # @commands.Cog.listener()
    # async def on_guild_channel_create(self, channel):
    #     if isinstance(channel, discord.TextChannel):
    #         webhook = await self.get_webhook(channel, "yuki")
    #         if webhook is None:
    #             await channel.create_webhook(name="yuki")

    # Webhook creation disabled - no longer auto-creating webhooks
    # @commands.Cog.listener()
    # async def on_guild_join(self, guild):
    #     for channel in guild.text_channels:
    #         webhook = await self.get_webhook(channel, "yuki")
    #         if webhook is None:
    #             await channel.create_webhook(name="yuki")



    @commands.group(invoke_without_command=True)
    async def reskin(self, ctx):
        return await ctx.create_pages()

    @reskin.command()
    async def delete(self, ctx: commands.Context): 
      await self.bot.db.execute("DELETE FROM reskin WHERE user_id = $1", ctx.author.id)
      await ctx.send_success("Your reskin has been successfuly deleted")

    
    @reskin.command()
    async def name(self, ctx, *, name: str):
        existing_entry = await self.bot.db.fetchrow("SELECT * FROM reskin WHERE user_id = $1", ctx.author.id)
        if existing_entry:
            await self.bot.db.execute("UPDATE reskin SET name = $1 WHERE user_id = $2", name, ctx.author.id)
        else:
            await self.bot.db.execute("INSERT INTO reskin VALUES ($1, $2, $3)", ctx.author.id, ctx.author.avatar.url, name)
        await ctx.send_success(f"Your reskin name its {name}")


    @reskin.command()
    async def avatar(self, ctx, avatar: str):
        existing_entry = await self.bot.db.fetchrow("SELECT * FROM reskin WHERE user_id = $1", ctx.author.id)
        if existing_entry:
            await self.bot.db.execute("UPDATE reskin SET avatar_url = $1 WHERE user_id = $2", avatar, ctx.author.id)
        else:
            await self.bot.db.execute("INSERT INTO reskin VALUES ($1, $2, $3)", ctx.author.id, avatar, ctx.author.name)
        await ctx.send_success("Successfuly set your reskin avatar")


    @reskin.command()
    async def webhook(self, ctx):
        # This command is deprecated - webhooks are now created on-demand only
        await ctx.send_warning("Webhooks are now created automatically when needed for reskin functionality.")
    
    @reskin.command()
    async def cleanup(self, ctx):
        """Delete all 'yuki' webhooks from the server"""
        deleted = 0
        for channel in ctx.guild.text_channels:
            try:
                webhooks = await channel.webhooks()
                for webhook in webhooks:
                    if webhook.name == "yuki":
                        await webhook.delete(reason=f"Cleanup requested by {ctx.author}")
                        deleted += 1
            except:
                continue
        
        if deleted > 0:
            await ctx.send_success(f"Deleted {deleted} 'yuki' webhook{'s' if deleted != 1 else ''} from the server.")
        else:
            await ctx.send_warning("No 'yuki' webhooks found in this server.")
   
    @reskin.command()
    async def preview(self, ctx):
        webhook = await self.get_webhook(ctx.channel, "yuki")
        results = await self.bot.db.fetch("SELECT * FROM reskin WHERE user_id = $1", ctx.author.id) 
        if results is None:
            return
        if webhook is not None:
            avurl = results[0]['avatar_url']

            name = results[0]['name']
            await webhook.send("haiii >.<", username=name, avatar_url=avurl)
        else:
            await ctx.send("webhook not  found, so i'll send the message")
        
        
async def setup(bot):
    await bot.add_cog(reskin(bot))
