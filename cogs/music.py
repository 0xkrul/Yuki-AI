import asyncio
import random
import discord
import pomice
from discord.ext import commands


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.node = None
        self.node_ready = asyncio.Event()

    async def cog_load(self):
        await self.init_node()
    
    async def get_dj(self, guild_id: int, channel_id: int):
        """Get the DJ for a voice channel"""
        result = await self.bot.db.fetchrow(
            "SELECT dj_id FROM music_dj WHERE guild_id = $1 AND channel_id = $2",
            guild_id, channel_id
        )
        return result["dj_id"] if result else None
    
    async def set_dj(self, guild_id: int, channel_id: int, user_id: int):
        """Set the DJ for a voice channel"""
        existing = await self.bot.db.fetchrow(
            "SELECT * FROM music_dj WHERE guild_id = $1 AND channel_id = $2",
            guild_id, channel_id
        )
        if existing:
            await self.bot.db.execute(
                "UPDATE music_dj SET dj_id = $1 WHERE guild_id = $2 AND channel_id = $3",
                user_id, guild_id, channel_id
            )
        else:
            await self.bot.db.execute(
                "INSERT INTO music_dj VALUES ($1, $2, $3)",
                guild_id, channel_id, user_id
            )
    
    async def is_mixer(self, guild_id: int, channel_id: int, user_id: int):
        """Check if a user is a mixer for a voice channel"""
        result = await self.bot.db.fetchrow(
            "SELECT * FROM music_mixers WHERE guild_id = $1 AND channel_id = $2 AND mixer_id = $3",
            guild_id, channel_id, user_id
        )
        return result is not None
    
    async def add_mixer(self, guild_id: int, channel_id: int, user_id: int):
        """Add a mixer for a voice channel"""
        existing = await self.bot.db.fetchrow(
            "SELECT * FROM music_mixers WHERE guild_id = $1 AND channel_id = $2 AND mixer_id = $3",
            guild_id, channel_id, user_id
        )
        if not existing:
            await self.bot.db.execute(
                "INSERT INTO music_mixers VALUES ($1, $2, $3)",
                guild_id, channel_id, user_id
            )
    
    async def remove_mixer(self, guild_id: int, channel_id: int, user_id: int):
        """Remove a mixer from a voice channel"""
        await self.bot.db.execute(
            "DELETE FROM music_mixers WHERE guild_id = $1 AND channel_id = $2 AND mixer_id = $3",
            guild_id, channel_id, user_id
        )
    
    async def get_mixers(self, guild_id: int, channel_id: int):
        """Get all mixers for a voice channel"""
        results = await self.bot.db.fetch(
            "SELECT mixer_id FROM music_mixers WHERE guild_id = $1 AND channel_id = $2",
            guild_id, channel_id
        )
        return [r["mixer_id"] for r in results]
    
    async def can_control_music(self, ctx):
        """Check if user can control music (DJ, mixer, or manage_channels permission)"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return False, "You need to be in a voice channel to control music."
        
        channel_id = ctx.author.voice.channel.id
        guild_id = ctx.guild.id
        
        # Check if user has manage_channels permission
        if ctx.author.guild_permissions.manage_channels:
            return True, None
        
        # Check if user is the DJ
        dj_id = await self.get_dj(guild_id, channel_id)
        if dj_id == ctx.author.id:
            return True, None
        
        # Check if user is a mixer
        if await self.is_mixer(guild_id, channel_id, ctx.author.id):
            return True, None
        
        # User doesn't have permission
        dj_mention = f"<@{dj_id}>" if dj_id else "a DJ"
        return False, f"Only the DJ ({dj_mention}) or mixers can control the music. Ask someone with **Manage Channels** permission to set you as DJ or mixer."

    async def init_node(self):
        try:
            self.node = await pomice.NodePool.create_node(
                bot=self.bot,
                host="audio.rive.wtf",
                port=24597,
                password="youshallnotpass",
                identifier="primary",
                secure=False,
                spotify_client_id="a65ad4c0ca0c45f58ad3bea1066d876c",
                spotify_client_secret="bce7617dc8c64f66997fdaa719af4fd4",
                apple_music=True,
            )
        except Exception:
            self.node = await pomice.NodePool.create_node(
                bot=self.bot,
                host="107.150.58.122",
                port=4006,
                password="https://discord.gg/mjS5J2K3ep",
                identifier="fallback",
                secure=False,
            )

        self.node_ready.set()

    async def get_player(self, ctx, connect=True):
        await self.node_ready.wait()

        if not ctx.author.voice:
            return None

        player = self.node.get_player(ctx.guild.id)

        if player is None and connect:
            channel = ctx.author.voice.channel
            if ctx.voice_client:
                await ctx.voice_client.move_to(channel)
            else:
                await channel.connect(cls=Player, self_deaf=True)

            player = self.node.get_player(ctx.guild.id)
            player.invoke_id = ctx.channel.id
            await player.set_volume(65)

        return player

    @commands.command()
    async def play(self, ctx, *, query: str):
        player = await self.get_player(ctx)
        if not player:
            return

        # Check if DJ is set - if not, allow play and auto-assign DJ
        if ctx.author.voice and ctx.author.voice.channel:
            channel_id = ctx.author.voice.channel.id
            dj_id = await self.get_dj(ctx.guild.id, channel_id)
            
            # If no DJ is set, allow this play and auto-assign them as DJ
            if not dj_id:
                # Allow the play, we'll assign DJ after successful track search
                pass
            else:
                # DJ is set, check permissions
                can_control, error_msg = await self.can_control_music(ctx)
                if not can_control:
                    await ctx.send(embed=discord.Embed(description=error_msg))
                    return

        try:
            results = await self.node.get_tracks(query=query, ctx=ctx)
        except Exception as e:
            await ctx.send(embed=discord.Embed(description=f"Failed to search for tracks: {str(e)}"))
            return

        if not results:
            await ctx.send(embed=discord.Embed(description="No tracks found."))
            return

        # Auto-assign DJ if no DJ is set (first song) - after successful track search
        if ctx.author.voice and ctx.author.voice.channel:
            channel_id = ctx.author.voice.channel.id
            dj_id = await self.get_dj(ctx.guild.id, channel_id)
            if not dj_id:
                await self.set_dj(ctx.guild.id, channel_id, ctx.author.id)
                await ctx.send(embed=discord.Embed(description=f"🎵 **{ctx.author.display_name}** is now the DJ!"))

        try:
            if isinstance(results, pomice.Playlist):
                for t in results.tracks:
                    setattr(t, "requester", ctx.author)
                    await player.enqueue(t)
                await ctx.send(embed=discord.Embed(description=f"Added playlist {results.name} ({len(results.tracks)} tracks)"))
            else:
                t = results[0]
                setattr(t, "requester", ctx.author)
                await player.enqueue(t)
                await ctx.send(embed=discord.Embed(description=f"Added {t.title}"))

            await player.ensure_running()
        except Exception as e:
            await ctx.send(embed=discord.Embed(description=f"Error adding track to queue: {str(e)}"))

    @commands.command()
    async def skip(self, ctx):
        # Check DJ permissions
        can_control, error_msg = await self.can_control_music(ctx)
        if not can_control:
            await ctx.send(embed=discord.Embed(description=error_msg))
            return
        
        print(f"[MUSIC DEBUG] Skip command called by {ctx.author} in guild {ctx.guild.id}")
        player = await self.get_player(ctx, connect=False)
        if not player:
            await ctx.send(embed=discord.Embed(description="No player found. Make sure the bot is playing music."))
            return
        
        current_track = getattr(player, "_now_playing", None)
        queue_size = self._get_queue_size(player)
        
        print(f"[MUSIC DEBUG] Player found. Queue size: {queue_size}, Now playing: {current_track}")
        print(f"[MUSIC DEBUG] Loop task state: {player._loop_task is not None}, Done: {player._loop_task.done() if player._loop_task else 'N/A'}")
        
        if current_track:
            await ctx.send(embed=discord.Embed(description=f"Skipped **{current_track.title}**"))
        else:
            await ctx.send(embed=discord.Embed(description="Skipped current track"))
        
        await player.skip()
        print(f"[MUSIC DEBUG] Skip method completed. Queue size after: {self._get_queue_size(player)}")
    
    def _get_queue_size(self, player):
        """Helper to get queue size safely"""
        try:
            return player.queue.qsize()
        except:
            try:
                return len(list(player.queue._queue))
            except:
                return 0

    @commands.command()
    async def skipto(self, ctx, index: int):
        # Check DJ permissions
        can_control, error_msg = await self.can_control_music(ctx)
        if not can_control:
            await ctx.send(embed=discord.Embed(description=error_msg))
            return
        player = await self.get_player(ctx, connect=False)
        if not player:
            await ctx.send(embed=discord.Embed(description="No player found. Make sure the bot is playing music."))
            return
        
        if index < 0:
            await ctx.send(embed=discord.Embed(description="Invalid index. Use a number 0 or greater."))
            return

        # Get current queue items
        try:
            items = list(player.queue._queue)
        except Exception as e:
            print(f"[MUSIC DEBUG] Error getting queue items: {e}")
            await ctx.send(embed=discord.Embed(description="Error accessing queue."))
            return

        if index >= len(items):
            await ctx.send(embed=discord.Embed(description=f"Index {index} is out of range. Queue has {len(items)} track(s) (0-{len(items)-1})."))
            return

        # Use 0-based indexing directly (index 0 = first in queue, not currently playing)
        # Currently playing track is not in the queue, it's in _now_playing
        target_index = index  # Already 0-based
        target_track = items[target_index]
        
        print(f"[MUSIC DEBUG] skipto: index={index} (1-based), target_index={target_index} (0-based), target={target_track.title}")
        print(f"[MUSIC DEBUG] Queue items: {[t.title for t in items]}")
        
        # We want to preserve all tracks except:
        # 1. Index 0 (currently playing track) - remove it
        # 2. The target track (target_index) - move it to first position
        
        # Get tracks before the target (from index 1 up to but not including target_index)
        # Get tracks after the target (from target_index+1 to end)
        # Then combine them in order
        
        if target_index <= 0:
            # If target is at index 0 or invalid, just preserve everything after index 0
            tracks_to_preserve = items[1:] if len(items) > 1 else []
        else:
            # Get tracks from index 1 to target_index (before target, excluding index 0)
            # But we need to exclude the target itself, so we go up to target_index (exclusive in slice)
            # Example: items=[0,1,2,3,4], target_index=2 -> items[1:2] = [1] ✓
            # Example: items=[0,1,2,3,4], target_index=1 -> items[1:1] = [] ✗ (should be empty, target is at 1)
            # Actually wait, if target_index=1, there are no tracks before it (only index 0 which we exclude)
            # So items[1:1] = [] is correct!
            
            # Get tracks before target (from 1 to target_index, exclusive)
            tracks_before = items[1:target_index]  # This will be [] if target_index <= 1, which is correct
            # Get tracks after target
            tracks_after = items[target_index + 1:] if target_index + 1 < len(items) else []
            # Combine: all tracks except index 0 and target_index
            tracks_to_preserve = list(tracks_before) + list(tracks_after)
            print(f"[MUSIC DEBUG] tracks_before (items[1:{target_index}]): {[t.title for t in tracks_before]}, tracks_after (items[{target_index+1}:]): {[t.title for t in tracks_after]}")
        
        print(f"[MUSIC DEBUG] tracks_to_preserve: {[t.title for t in tracks_to_preserve]}")
        
        # Clear and rebuild queue: [target, ...before (excluding current), ...after]
        player.queue._queue.clear()
        
        # Put target first
        await player.queue.put(target_track)
        
        # Put all preserved tracks (they're already in the correct order)
        for t in tracks_to_preserve:
            await player.queue.put(t)

        preserved_count = len(tracks_to_preserve)
        await ctx.send(embed=discord.Embed(description=f"Skipping to **{target_track.title}** (removed currently playing track, preserved {preserved_count} track(s) before it)"))
        await player.skip()

    @commands.command()
    async def shuffle(self, ctx):
        # Check DJ permissions
        can_control, error_msg = await self.can_control_music(ctx)
        if not can_control:
            await ctx.send(embed=discord.Embed(description=error_msg))
            return
        player = await self.get_player(ctx, connect=False)
        if not player:
            await ctx.send(embed=discord.Embed(description="No player found. Make sure the bot is playing music."))
            return

        try:
            items = list(player.queue._queue)
        except Exception as e:
            print(f"[MUSIC DEBUG] Error getting queue items: {e}")
            await ctx.send(embed=discord.Embed(description="Error accessing queue."))
            return

        if not items:
            await ctx.send(embed=discord.Embed(description="Queue is empty. Nothing to shuffle."))
            return

        random.shuffle(items)
        player.queue._queue.clear()
        for t in items:
            await player.queue.put(t)

        await ctx.send(embed=discord.Embed(description=f"Shuffled {len(items)} track(s) in the queue."))

    @commands.command()
    async def remove(self, ctx, index: int):
        # Check DJ permissions
        can_control, error_msg = await self.can_control_music(ctx)
        if not can_control:
            await ctx.send(embed=discord.Embed(description=error_msg))
            return
        player = await self.get_player(ctx, connect=False)
        if not player:
            await ctx.send(embed=discord.Embed(description="No player found. Make sure the bot is playing music."))
            return
        
        if index < 1:
            await ctx.send(embed=discord.Embed(description="Invalid index. Use a number greater than 0."))
            return

        try:
            items = list(player.queue._queue)
        except Exception as e:
            print(f"[MUSIC DEBUG] Error getting queue items: {e}")
            await ctx.send(embed=discord.Embed(description="Error accessing queue."))
            return

        if index > len(items):
            await ctx.send(embed=discord.Embed(description=f"Index {index} is out of range. Queue has {len(items)} track(s)."))
            return

        removed_track = items.pop(index - 1)
        
        player.queue._queue.clear()
        for t in items:
            await player.queue.put(t)

        await ctx.send(embed=discord.Embed(description=f"Removed **{removed_track.title}** from the queue. {len(items)} track(s) remaining."))

    @commands.command()
    async def queue(self, ctx):
        player = await self.get_player(ctx, connect=False)
        if not player:
            return

        lines = []
        now = getattr(player, "_now_playing", None)
        if now is not None:
            lines.append(f"Now playing: {now.title}")

        upcoming = list(player.queue._queue)
        if upcoming:
            for i, t in enumerate(upcoming[:15], start=1):
                lines.append(f"{i}. {t.title}")

        if not lines:
            return

        await ctx.send(embed=discord.Embed(description="\n".join(lines)))

    @commands.Cog.listener()
    async def on_pomice_track_end(self, *args, **kwargs):
        # Pomice events - the first argument IS the player, not an event with a player attribute
        player = args[0] if args else None
        print(f"[MUSIC DEBUG] on_pomice_track_end event received, args count: {len(args)}, player: {player}")
        if player and isinstance(player, Player):
            print(f"[MUSIC DEBUG] Calling mark_track_done from track_end event for guild {player.guild.id}")
            player.mark_track_done()
        else:
            print(f"[MUSIC DEBUG] Track end event - player is not Player instance: {type(player)}")

    @commands.Cog.listener()
    async def on_pomice_track_exception(self, *args, **kwargs):
        player = args[0] if args else None
        if player and isinstance(player, Player):
            print(f"[MUSIC DEBUG] Track exception event for guild {player.guild.id}")
            player.mark_track_done()

    @commands.Cog.listener()
    async def on_pomice_track_stuck(self, *args, **kwargs):
        player = args[0] if args else None
        if player and isinstance(player, Player):
            print(f"[MUSIC DEBUG] Track stuck event for guild {player.guild.id}")
            player.mark_track_done()
    
    @commands.group(invoke_without_command=True)
    async def dj(self, ctx):
        """DJ management commands"""
        await ctx.create_pages()
    
    @dj.command(name="set")
    async def dj_set(self, ctx, member: discord.Member = None):
        """Set the DJ for the current voice channel (requires Manage Channels permission)"""
        if not ctx.author.guild_permissions.manage_channels:
            await ctx.send(embed=discord.Embed(description="You need **Manage Channels** permission to set the DJ."))
            return
        
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=discord.Embed(description="You need to be in a voice channel to set the DJ."))
            return
        
        if member is None:
            member = ctx.author
        
        if member.voice is None or member.voice.channel != ctx.author.voice.channel:
            await ctx.send(embed=discord.Embed(description=f"**{member.display_name}** must be in the same voice channel as you."))
            return
        
        channel_id = ctx.author.voice.channel.id
        await self.set_dj(ctx.guild.id, channel_id, member.id)
        await ctx.send(embed=discord.Embed(description=f"🎵 **{member.display_name}** is now the DJ for {ctx.author.voice.channel.mention}!"))
    
    @dj.command(name="current", aliases=["who", "info"])
    async def dj_current(self, ctx):
        """Show the current DJ for the voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=discord.Embed(description="You need to be in a voice channel."))
            return
        
        channel_id = ctx.author.voice.channel.id
        dj_id = await self.get_dj(ctx.guild.id, channel_id)
        
        if not dj_id:
            await ctx.send(embed=discord.Embed(description=f"No DJ set for {ctx.author.voice.channel.mention}. The first person to play a song will become the DJ."))
            return
        
        dj = ctx.guild.get_member(dj_id)
        if not dj:
            await ctx.send(embed=discord.Embed(description=f"DJ is set to <@{dj_id}> (user not found in server)."))
            return
        
        mixers = await self.get_mixers(ctx.guild.id, channel_id)
        mixer_mentions = [f"<@{m}>" for m in mixers] if mixers else ["None"]
        
        embed = discord.Embed(
            title=f"DJ Info for {ctx.author.voice.channel.name}",
            description=f"**DJ:** {dj.mention}\n**Mixers:** {', '.join(mixer_mentions)}"
        )
        await ctx.send(embed=embed)
    
    @dj.group(name="mixer", invoke_without_command=True)
    async def dj_mixer(self, ctx):
        """Manage mixers (secondary DJs)"""
        await ctx.create_pages()
    
    @dj_mixer.command(name="add")
    async def mixer_add(self, ctx, member: discord.Member = None):
        """Add a mixer (requires DJ or Manage Channels permission)"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=discord.Embed(description="You need to be in a voice channel."))
            return
        
        if member is None:
            member = ctx.author
        
        if member.voice is None or member.voice.channel != ctx.author.voice.channel:
            await ctx.send(embed=discord.Embed(description=f"**{member.display_name}** must be in the same voice channel as you."))
            return
        
        channel_id = ctx.author.voice.channel.id
        guild_id = ctx.guild.id
        
        # Check if user is DJ or has manage_channels
        dj_id = await self.get_dj(guild_id, channel_id)
        is_dj = dj_id == ctx.author.id
        has_perms = ctx.author.guild_permissions.manage_channels
        
        if not is_dj and not has_perms:
            await ctx.send(embed=discord.Embed(description="Only the DJ or someone with **Manage Channels** permission can add mixers."))
            return
        
        if await self.is_mixer(guild_id, channel_id, member.id):
            await ctx.send(embed=discord.Embed(description=f"**{member.display_name}** is already a mixer."))
            return
        
        await self.add_mixer(guild_id, channel_id, member.id)
        await ctx.send(embed=discord.Embed(description=f"🎧 **{member.display_name}** is now a mixer!"))
    
    @dj_mixer.command(name="remove", aliases=["rm"])
    async def mixer_remove(self, ctx, member: discord.Member = None):
        """Remove a mixer (requires DJ or Manage Channels permission)"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=discord.Embed(description="You need to be in a voice channel."))
            return
        
        if member is None:
            member = ctx.author
        
        channel_id = ctx.author.voice.channel.id
        guild_id = ctx.guild.id
        
        # Check if user is DJ or has manage_channels
        dj_id = await self.get_dj(guild_id, channel_id)
        is_dj = dj_id == ctx.author.id
        has_perms = ctx.author.guild_permissions.manage_channels
        
        if not is_dj and not has_perms:
            await ctx.send(embed=discord.Embed(description="Only the DJ or someone with **Manage Channels** permission can remove mixers."))
            return
        
        if not await self.is_mixer(guild_id, channel_id, member.id):
            await ctx.send(embed=discord.Embed(description=f"**{member.display_name}** is not a mixer."))
            return
        
        await self.remove_mixer(guild_id, channel_id, member.id)
        await ctx.send(embed=discord.Embed(description=f"**{member.display_name}** is no longer a mixer."))
    
    @dj_mixer.command(name="list")
    async def mixer_list(self, ctx):
        """List all mixers for the current voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=discord.Embed(description="You need to be in a voice channel."))
            return
        
        channel_id = ctx.author.voice.channel.id
        mixers = await self.get_mixers(ctx.guild.id, channel_id)
        
        if not mixers:
            await ctx.send(embed=discord.Embed(description=f"No mixers set for {ctx.author.voice.channel.mention}."))
            return
        
        mixer_list = []
        for mixer_id in mixers:
            mixer = ctx.guild.get_member(mixer_id)
            if mixer:
                mixer_list.append(f"• {mixer.mention} ({mixer.display_name})")
            else:
                mixer_list.append(f"• <@{mixer_id}> (user not found)")
        
        embed = discord.Embed(
            title=f"Mixers for {ctx.author.voice.channel.name}",
            description="\n".join(mixer_list) if mixer_list else "No mixers"
        )
        await ctx.send(embed=embed)


class Player(pomice.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = asyncio.Queue()
        self.invoke_id = None
        self._loop_task = None
        self._advance_lock = asyncio.Lock()
        self._skip_lock = asyncio.Lock()  # Lock for skip operations to prevent race conditions
        self._track_done = asyncio.Event()
        self._now_playing = None
        self._skip_requested = False

        if hasattr(self, "add_event_hook"):
            try:
                self.add_event_hook(self._event_hook)
            except Exception:
                pass

    async def enqueue(self, track):
        await self.queue.put(track)

    def mark_track_done(self):
        print(f"[MUSIC DEBUG] mark_track_done() called for guild {self.guild.id}")
        self._track_done.set()

    async def _event_hook(self, event):
        name = event.__class__.__name__
        print(f"[MUSIC DEBUG] Event hook received: {name} for guild {self.guild.id}")
        if name in ("TrackEndEvent", "TrackExceptionEvent", "TrackStuckEvent"):
            print(f"[MUSIC DEBUG] Marking track done due to event: {name} for guild {self.guild.id}")
            self.mark_track_done()

    async def ensure_running(self):
        if self._loop_task and not self._loop_task.done():
            print(f"[MUSIC DEBUG] Playback loop already running for guild {self.guild.id}")
            return
        print(f"[MUSIC DEBUG] Starting playback loop for guild {self.guild.id}, queue size: {self.queue.qsize()}")
        self._loop_task = asyncio.create_task(self._playback_loop())

    async def _playback_loop(self):
        print(f"[MUSIC DEBUG] Playback loop started for guild {self.guild.id}")
        iteration = 0
        try:
            while True:
                iteration += 1
                queue_size = self.queue.qsize()
                print(f"[MUSIC DEBUG] Loop iteration {iteration} for guild {self.guild.id}, queue size: {queue_size}")
                
                if self.queue.empty():
                    print(f"[MUSIC DEBUG] Queue empty, exiting loop for guild {self.guild.id}")
                    break

                track = None
                async with self._advance_lock:
                    if self.queue.empty():
                        print(f"[MUSIC DEBUG] Queue became empty while acquiring lock, exiting for guild {self.guild.id}")
                        break

                    track = await self.queue.get()
                    self._now_playing = track
                    self._track_done.clear()
                    self._skip_requested = False
                    print(f"[MUSIC DEBUG] Got track from queue: {track.title} for guild {self.guild.id}")

                # Play track outside the lock to avoid blocking
                try:
                    print(f"[MUSIC DEBUG] Attempting to play track: {track.title} for guild {self.guild.id}")
                    await self.play(track)
                    print(f"[MUSIC DEBUG] Successfully started playing: {track.title} for guild {self.guild.id}")
                except Exception as e:
                    print(f"[MUSIC DEBUG] ERROR playing track {track.title}: {e} for guild {self.guild.id}")
                    import traceback
                    traceback.print_exc()
                    # If play fails, skip to next track
                    self._now_playing = None
                    continue

                if self.invoke_id:
                    ch = self.guild.get_channel(self.invoke_id)
                    if ch:
                        try:
                            await ch.send(embed=discord.Embed(description=f"Now playing {track.title}"))
                        except Exception as e:
                            print(f"[MUSIC DEBUG] Failed to send now playing message: {e}")

                print(f"[MUSIC DEBUG] Waiting for track to finish: {track.title} for guild {self.guild.id}")
                await self._wait_until_finished(track)
                print(f"[MUSIC DEBUG] Track finished/skipped: {track.title} for guild {self.guild.id}, queue size now: {self.queue.qsize()}")
                
                # Clear now playing after track finishes
                self._now_playing = None
                
                # Small delay to prevent rapid looping
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            print(f"[MUSIC DEBUG] Playback loop cancelled for guild {self.guild.id}")
            raise
        except Exception as e:
            print(f"[MUSIC DEBUG] Error in playback loop: {e} for guild {self.guild.id}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"[MUSIC DEBUG] Playback loop ending for guild {self.guild.id}, destroying player")
            self._now_playing = None
            try:
                await self.destroy()
            except Exception as e:
                print(f"[MUSIC DEBUG] Error destroying player: {e}")

    async def _wait_until_finished(self, track):
        length_ms = getattr(track, "length", None)
        print(f"[MUSIC DEBUG] Waiting for track to finish: {track.title}, length: {length_ms}ms for guild {self.guild.id}")
        
        # Instead of one long sleep, break it into chunks and check for skip/done
        if isinstance(length_ms, int) and length_ms > 0:
            total_sleep = max(0.0, (length_ms / 1000.0) - 1.0)
            print(f"[MUSIC DEBUG] Will sleep for {total_sleep}s total, checking every 0.5s for skip/done for guild {self.guild.id}")
            
            # Sleep in chunks of 0.5 seconds, checking for skip/done between chunks
            chunks = int(total_sleep / 0.5)
            remainder = total_sleep % 0.5
            
            for i in range(chunks):
                if self._track_done.is_set():
                    print(f"[MUSIC DEBUG] Track done during sleep chunk {i+1}/{chunks} for {track.title} for guild {self.guild.id}")
                    return
                if self._skip_requested:
                    print(f"[MUSIC DEBUG] Skip requested during sleep chunk {i+1}/{chunks} for {track.title} for guild {self.guild.id}")
                    return
                await asyncio.sleep(0.5)
            
            if remainder > 0:
                if self._track_done.is_set() or self._skip_requested:
                    print(f"[MUSIC DEBUG] Track done/skip during final sleep for {track.title} for guild {self.guild.id}")
                    return
                await asyncio.sleep(remainder)

        stable_off = 0
        check_count = 0
        while True:
            check_count += 1
            if check_count % 10 == 0:  # Log every 10 checks to avoid spam
                print(f"[MUSIC DEBUG] Still waiting for track {track.title} (check #{check_count}), track_done: {self._track_done.is_set()}, skip_requested: {self._skip_requested} for guild {self.guild.id}")
            
            if self._track_done.is_set():
                print(f"[MUSIC DEBUG] Track done event set for {track.title} for guild {self.guild.id}")
                return

            if self._skip_requested:
                print(f"[MUSIC DEBUG] Skip requested for {track.title} for guild {self.guild.id}")
                return

            playing = False
            try:
                playing = bool(getattr(self, "is_playing", False))
            except Exception as e:
                print(f"[MUSIC DEBUG] Error checking is_playing: {e} for guild {self.guild.id}")
                playing = False

            if not playing:
                stable_off += 1
                if stable_off >= 3:
                    print(f"[MUSIC DEBUG] Track stopped playing (stable_off={stable_off}) for {track.title} for guild {self.guild.id}")
                    return
            else:
                stable_off = 0

            await asyncio.sleep(0.35)

    async def skip(self):
        # Use lock to prevent multiple simultaneous skips
        async with self._skip_lock:
            print(f"[MUSIC DEBUG] Skip method called for guild {self.guild.id}")
            print(f"[MUSIC DEBUG] Before skip - queue size: {self.queue.qsize()}, now playing: {getattr(self, '_now_playing', None)}, loop task: {self._loop_task is not None}")
            
            # Set skip flags first to ensure immediate detection
            self._skip_requested = True
            self.mark_track_done()
            print(f"[MUSIC DEBUG] Set skip flags for guild {self.guild.id}")
            
            # Stop the current track
            try:
                await self.stop()
                print(f"[MUSIC DEBUG] Stopped player for guild {self.guild.id}")
            except Exception as e:
                print(f"[MUSIC DEBUG] Error stopping player: {e} for guild {self.guild.id}")
                import traceback
                traceback.print_exc()
            
            # Small delay to ensure stop completes before checking queue
            await asyncio.sleep(0.1)
            
            # Ensure playback loop continues if there are more tracks
            queue_empty = self.queue.empty()
            print(f"[MUSIC DEBUG] After stop - queue empty: {queue_empty}, queue size: {self.queue.qsize()}")
            
            if not queue_empty:
                loop_running = self._loop_task is not None and not self._loop_task.done()
                print(f"[MUSIC DEBUG] Queue not empty, ensuring loop runs. Loop currently running: {loop_running} for guild {self.guild.id}")
                # Only ensure running if loop is not already running
                if not loop_running:
                    await self.ensure_running()
            else:
                print(f"[MUSIC DEBUG] Queue is empty, not restarting loop for guild {self.guild.id}")


async def setup(bot):
    await bot.add_cog(Music(bot))
