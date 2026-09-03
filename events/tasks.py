from discord.ext import tasks, commands
import discord, asyncio, random, datetime
from handlers.pfps import PFPS

async def get_genre(category): 
  if category == "male_pfps": return random.choice(PFPS.male)
  elif category == "female_pfps": return random.choice(PFPS.female)
  elif category == "anime_pfps": return random.choice(PFPS.anime)
  elif category == "male_gifs": return random.choice(PFPS.male_gif)
  elif category == "female_gifs": return random.choice(PFPS.female_gif)
  elif category == "anime_gifs": return random.choice(PFPS.anime_gif)
  elif category == "banners": return random.choice(PFPS.banner)


@tasks.loop(minutes=10)
async def counter_update(bot: commands.AutoShardedBot): 
  results = await bot.db.fetch("SELECT * FROM counters")
  for result in results: 
   channel = bot.get_channel(int(result["channel_id"]))
   if channel: 
    guild = channel.guild 
    module = result["module"]
    if module == "members": target = str(guild.member_count)
    elif module == "humans": target = str(len([m for m in guild.members if not m.bot]))
    elif module == "bots": target = str(len([m for m in guild.members if m.bot])) 
    elif module == "boosters": target = str(len(guild.premium_subscribers))
    elif module == "voice": target = str(sum(len(c.members) for c in guild.voice_channels))     
    name = result["channel_name"].replace("{target}", target)
    await channel.edit(name=name, reason="updating counter")         

@tasks.loop(hours=6)
async def delete(bot):
   lis = ["snipe", "reactionsnipe", "editsnipe"]
   for l in lis: await bot.db.execute(f"DELETE FROM {l}")  

@tasks.loop(minutes=1)
async def autopfp(bot: commands.AutoShardedBot): 
    results = await bot.db.fetch("SELECT * FROM autopfp")
    if not results:
        # Silently skip if no autopfp entries - no spam logging
        return

    for result in results: 
        print(f"Processing autopfp for {result}")

        genre = result['genre']
        pfp_type = result['type']

        if genre == "random":
            links = await get_genre(random.choice([
                "anime_pfps", "anime_gifs",
                "male_pfps", "male_gifs",
                "female_pfps", "female_gifs"
            ]))
        elif genre == "banner":
            links = await get_genre("banners")
        else:
            links = await get_genre(f"{genre}_{pfp_type}s")

        if not links:
            print(f"No links found for genre {genre}, type {pfp_type}")
            continue

        embed = (
            discord.Embed(
                color=bot.color,
                title="pfps source",
                url="https://pinterest.com/antipfps"
            )
            .set_author(
                name="follow the pinterest",
                icon_url="https://cdn.discordapp.com/emojis/1026647994390552666.webp?size=240&quality=lossless"
            )
        )
        embed.set_image(url=links)
        embed.timestamp = datetime.datetime.utcnow()

        channel_id = int(result['channel_id'])
        channel = bot.get_channel(channel_id)

        if channel:
            print(f"Sending autopfp to {channel.name} in {channel.guild.name}")
            try:
                await channel.send(embed=embed)
                await asyncio.sleep(30)
            except Exception as e:
                print(f"Failed to send embed: {e}")
        else:
            print(f"Channel {channel_id} not found")
   
             
class Tasks(commands.Cog): 
    def __init__(self, bot: commands.AutoShardedBot): 
      self.bot = bot 

    @commands.Cog.listener()
    async def on_ready(self): 
        await self.bot.wait_until_ready()
        if not counter_update.is_running():
            counter_update.start(self.bot)
        if not delete.is_running():
            delete.start(self.bot)       
        if not autopfp.is_running():
            autopfp.start(self.bot)


async def setup(bot: commands.AutoShardedBot) -> None:
    await bot.add_cog(Tasks(bot))                 
