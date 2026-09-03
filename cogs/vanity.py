import discord
from discord.ext import commands, tasks

class Vanity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="vanity", invoke_without_command=True)
    async def vanity(self, ctx):
        return await ctx.create_pages()

    @vanity.command(name="set")
    @commands.has_permissions(administrator=True)
    async def set_vanity(self, ctx, *, phrase: str):
        await self.bot.db.execute(
            "INSERT INTO vanity_settings(guild_id, vanity_phrase) VALUES($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET vanity_phrase = $2",
            ctx.guild.id, phrase
        )
        await ctx.send_success(f"Vanity phrase set to: `{phrase}`")

    @vanity.command(name="role")
    @commands.has_permissions(administrator=True)
    async def set_role(self, ctx, role: discord.Role):
        await self.bot.db.execute(
            "INSERT INTO vanity_settings(guild_id, role_id) VALUES($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET role_id = $2",
            ctx.guild.id, role.id
        )
        await ctx.send_success(f"Vanity role set to: {role.mention}")

    @vanity.command(name="settings")
    async def vanity_settings(self, ctx):
        row = await self.bot.db.fetchrow(
            "SELECT vanity_phrase, role_id FROM vanity_settings WHERE guild_id = $1",
            ctx.guild.id
        )
        if row:
            role = ctx.guild.get_role(row["role_id"]) if row["role_id"] else None
            await ctx.send(f"Vanity phrase: `{row['vanity_phrase']}`\nRole: {role.mention if role else 'Not set'}")
        else:
            await ctx.send_warning("No vanity settings found for this server.")

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        user = after
        guild = after.guild
        try:
            row = await self.bot.db.fetchrow(
                "SELECT vanity_phrase, role_id FROM vanity_settings WHERE guild_id = $1",
                guild.id
            )
            if not row:
                return

            vanity = row["vanity_phrase"]
            role_id = row["role_id"]

            try:
                ba = str(before.activity.name).lower()
            except:
                ba = "none"
            try:
                aa = str(after.activity.name).lower()
            except:
                aa = "none"

            if ba == aa:
                return

            role = guild.get_role(role_id)
            if not role:
                return

            if vanity.lower() in aa and vanity.lower() not in ba:
                try:
                    await after.add_roles(role, reason="yuki vanity: vanity in status")
                except:
                    pass

            elif vanity.lower() not in aa and vanity.lower() in ba:
                try:
                    await after.remove_roles(role, reason="yuki vanity: vanity removed from status")
                except:
                    pass

        except:
            pass


async def setup(bot):
    await bot.add_cog(Vanity(bot))
