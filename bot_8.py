import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re
import os
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Review channel where chatban panels are sent
REVIEW_CHANNEL_ID = 1501244015738093618

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=[".", "?"], intents=intents)
tree = bot.tree

# ── In-memory warnings ────────────────────────────────────────────────────────
warnings: dict[int, list[dict]] = {}

async def apply_warning_escalation(guild, member, count, channel):
    """Apply automatic punishment based on warning count."""

    # 3 warnings → 1 day chat ban
    if count == 3:
        await channel.send(embed=discord.Embed(
            title="🔇  Auto Chat Ban — 3 Warnings",
            description=f"{member.mention} has reached **3 warnings** and has been chat banned for **1 day**.",
            color=0xED4245,
        ))
        await do_chatban(guild, member, 86400, "Reached 3 warnings", guild.me)

    # 5 warnings → 1 week chat ban + last warning DM
    elif count == 5:
        await channel.send(embed=discord.Embed(
            title="🔇  Auto Chat Ban — 5 Warnings",
            description=f"{member.mention} has reached **5 warnings** and has been chat banned for **1 week**.",
            color=0xED4245,
        ))
        await do_chatban(guild, member, 604800, "Reached 5 warnings", guild.me)
        try:
            await member.send(embed=discord.Embed(
                title="⚠️  Last Warning",
                description="your on ur last warning, one more and you will be temporarily banned.",
                color=0xFEE75C,
            ))
        except discord.Forbidden:
            pass

    # 6+ warnings → 1 month temp ban
    elif count >= 6:
        await channel.send(embed=discord.Embed(
            title="🔨  Auto Temp Ban — 6 Warnings",
            description=f"{member.mention} has reached **{count} warnings** and has been temporarily banned for **1 month**.",
            color=0xED4245,
        ))
        try:
            await member.send(embed=discord.Embed(
                title="🔨  You've been temporarily banned",
                description=(
                    f"You have been temporarily banned from **{guild.name}** for 1 month "
                    f"due to reaching {count} warnings."
                ),
                color=0xED4245,
            ))
        except discord.Forbidden:
            pass
        await member.ban(reason=f"Reached {count} warnings — auto temp ban (1 month)")
        async def unban_after(g=guild, m=member):
            await asyncio.sleep(2592000)
            try:
                await g.unban(m, reason="Temp ban (1 month) expired")
                await m.send(embed=discord.Embed(
                    title="✅  Ban Lifted",
                    description=f"Your 1 month ban from **{g.name}** has expired. You may rejoin.",
                    color=0x57F287,
                ))
            except Exception:
                pass
        asyncio.create_task(unban_after())



# ── Additional mod stores ─────────────────────────────────────────────────────
mod_notes: dict[int, list[dict]] = {}
word_filter: set[str] = set()
antiraid_enabled = False
antispam_enabled = False

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_duration(time_str: str):
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = re.fullmatch(r"(\d+)([smhd])", time_str.strip().lower())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    return amount * units[unit]

def error_embed(desc): return discord.Embed(title="⚠️  Error", description=desc, color=0xED4245)
def success_embed(title, desc): return discord.Embed(title=title, description=desc, color=0x57F287)

async def get_member(guild, user):
    """Accept a Member object or int ID."""
    if isinstance(user, (discord.Member, discord.User)):
        return guild.get_member(user.id) or await guild.fetch_member(user.id)
    try:
        return await guild.fetch_member(int(user))
    except Exception:
        return None


# ── Chatban Review Panel ──────────────────────────────────────────────────────
class ChatbanReviewView(discord.ui.View):
    def __init__(self, guild_id, member_id, original_seconds, reason, moderator_id):
        super().__init__(timeout=None)
        self.guild_id        = guild_id
        self.member_id       = member_id
        self.original_seconds = original_seconds
        self.reason          = reason
        self.moderator_id    = moderator_id
        self.resolved        = False

    async def _resolve(self, interaction, action_embed):
        if self.resolved:
            await interaction.response.send_message(
                embed=error_embed("This case has already been resolved."), ephemeral=True
            )
            return False
        self.resolved = True
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        return True

    @discord.ui.button(label="⬆️  Increase Ban", style=discord.ButtonStyle.danger, custom_id="review_increase")
    async def increase_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True); return
        await interaction.response.send_modal(AdjustBanModal(self, action="increase"))

    @discord.ui.button(label="⬇️  Decrease Ban", style=discord.ButtonStyle.primary, custom_id="review_decrease")
    async def decrease_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True); return
        await interaction.response.send_modal(AdjustBanModal(self, action="decrease"))

    @discord.ui.button(label="✅  Remove Ban", style=discord.ButtonStyle.success, custom_id="review_remove")
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True); return
        if not await self._resolve(interaction, None):
            return
        guild  = bot.get_guild(self.guild_id)
        member = guild.get_member(self.member_id)
        if member:
            for channel in guild.text_channels:
                try:
                    await channel.set_permissions(member, send_messages=None,
                                          add_reactions=None,
                                          create_public_threads=None,
                                          create_private_threads=None,
                                          send_messages_in_threads=None, reason=f"Chatban removed by {interaction.user}")
                except discord.Forbidden:
                    pass
            try:
                await member.send(embed=discord.Embed(
                    title="🔊  Chat Ban Removed",
                    description=f"Your chat ban in **{guild.name}** has been reviewed and removed by a higher up.",
                    color=0x57F287,
                ))
            except discord.Forbidden:
                pass

        result_embed = discord.Embed(
            title="✅  Chat Ban Removed",
            description=(
                f"**User:** <@{self.member_id}>\n**Action:** Ban fully removed\n**Reviewed by:** {interaction.user.mention}"
            ),
            color=0x57F287,
        )
        await interaction.message.edit(embed=result_embed, view=self)
        await interaction.response.send_message(embed=success_embed("✅  Done", "Chat ban removed."), ephemeral=True)

    @discord.ui.button(label="✔️  Keep Ban", style=discord.ButtonStyle.secondary, custom_id="review_keep")
    async def keep_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True); return
        if not await self._resolve(interaction, None):
            return
        result_embed = discord.Embed(
            title="✔️  Chat Ban Kept",
            description=(
                f"**User:** <@{self.member_id}>\n**Decision:** Original ban upheld\n**Reviewed by:** {interaction.user.mention}"
            ),
            color=0x5865F2,
        )
        await interaction.message.edit(embed=result_embed, view=self)
        await interaction.response.send_message(embed=success_embed("✅  Done", "Ban upheld."), ephemeral=True)


class AdjustBanModal(discord.ui.Modal, title="Adjust Chat Ban Duration"):
    def __init__(self, review_view: ChatbanReviewView, action: str):
        super().__init__()
        self.review_view = review_view
        self.action      = action

    new_duration = discord.ui.TextInput(
        label="New duration",
        placeholder="e.g. 30m, 6h, 3d",
        min_length=2,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        seconds = parse_duration(self.new_duration.value.strip())
        if not seconds:
            await interaction.response.send_message(
                embed=error_embed("Invalid duration. Use `30m`, `6h`, `3d` etc."), ephemeral=True
            )
            return

        if not await self.review_view._resolve(interaction, None):
            return

        guild  = bot.get_guild(self.review_view.guild_id)
        member = guild.get_member(self.review_view.member_id)

        action_word = "increased" if self.action == "increase" else "decreased"
        color       = 0xED4245 if self.action == "increase" else 0x5865F2

        if member:
            # Reset permissions then reapply with new duration
            for channel in guild.text_channels:
                try:
                    await channel.set_permissions(member, send_messages=False,
                                          add_reactions=False,
                                          create_public_threads=False,
                                          create_private_threads=False,
                                          send_messages_in_threads=False,
                                                  reason=f"Chatban {action_word} by {interaction.user}")
                except discord.Forbidden:
                    pass
            expiry_ts = int(datetime.now(timezone.utc).timestamp()) + seconds
            try:
                await member.send(embed=discord.Embed(
                    title="🔇  Chat Ban Adjusted",
                    description=(
                        f"Your chat ban in **{guild.name}** has been {action_word} by a higher up.\n\n"
                        f"**New duration:** `{self.new_duration.value}`\n"
                        f"**Expires:** <t:{expiry_ts}:R>"
                    ),
                    color=color,
                ))
            except discord.Forbidden:
                pass
            asyncio.create_task(_chatban_expire(guild, member, seconds))

        result_embed = discord.Embed(
            title=f"{'⬆️' if self.action == 'increase' else '⬇️'}  Chat Ban {action_word.capitalize()}",
            description=(
                f"**User:** <@{self.review_view.member_id}>\n"
                f"**New Duration:** `{self.new_duration.value}`\n"
                f"**Reviewed by:** {interaction.user.mention}"
            ),
            color=color,
        )
        await interaction.message.edit(embed=result_embed, view=self.review_view)
        await interaction.response.send_message(
            embed=success_embed("✅  Done", f"Chat ban {action_word} to `{self.new_duration.value}`."), ephemeral=True
        )


async def send_review_panel(guild, member, seconds, reason, moderator):
    """Send a chatban review panel to the review channel."""
    review_channel = guild.get_channel(REVIEW_CHANNEL_ID)
    if not review_channel:
        return

    expiry_ts = int(datetime.now(timezone.utc).timestamp()) + seconds
    hours     = seconds // 3600
    duration_str = (
        f"{seconds // 86400}d" if seconds >= 86400
        else f"{hours}h" if seconds >= 3600
        else f"{seconds // 60}m" if seconds >= 60
        else f"{seconds}s"
    )

    embed = discord.Embed(
        title="📋  Chat Ban Review Request",
        description=(
            "A chat ban has been issued. Higher ups can review and adjust it below."
        ),
        color=0xFEE75C,
    )
    embed.add_field(name="👤  User",       value=f"{member.mention} (`{member.id}`)", inline=False)
    embed.add_field(name="⏱️  Duration",   value=f"`{duration_str}`", inline=True)
    embed.add_field(name="⌛  Expires",    value=f"<t:{expiry_ts}:R>", inline=True)
    embed.add_field(name="📝  Reason",     value=reason, inline=False)
    embed.add_field(name="🛡️  Issued by",  value=moderator.mention, inline=False)
    embed.set_footer(text="Only administrators can action this panel")

    view = ChatbanReviewView(
        guild_id=guild.id,
        member_id=member.id,
        original_seconds=seconds,
        reason=reason,
        moderator_id=moderator.id,
    )
    await review_channel.send(embed=embed, view=view)


async def do_chatban(guild, member, seconds, reason, moderator):
    expiry_ts = int(datetime.now(timezone.utc).timestamp()) + seconds
    failed = []
    for channel in guild.text_channels:
        try:
            await channel.set_permissions(member, send_messages=False,
                                          add_reactions=False,
                                          create_public_threads=False,
                                          create_private_threads=False,
                                          send_messages_in_threads=False,
                                          reason=f"Chat ban by {moderator} — {reason}")
        except discord.Forbidden:
            failed.append(channel.name)

    embed = discord.Embed(title="🔇  User Chat Banned", color=0xED4245)
    embed.add_field(name="User",      value=f"{member.mention} (`{member.id}`)", inline=False)
    embed.add_field(name="Duration",  value=f"`{seconds}s`", inline=True)
    embed.add_field(name="Expires",   value=f"<t:{expiry_ts}:R>", inline=True)
    embed.add_field(name="Reason",    value=reason, inline=False)
    embed.add_field(name="By",        value=moderator.mention, inline=False)
    if failed:
        embed.add_field(name="⚠️ Skipped channels", value=", ".join(failed[:10]), inline=False)

    try:
        await member.send(embed=discord.Embed(
            title="🔇  You've been chat banned",
            description=(
                f"You have been chat banned in **{guild.name}**.\n\n"
                f"**Reason:** {reason}\n**Expires:** <t:{expiry_ts}:R>"
            ),
            color=0xED4245,
        ))
    except discord.Forbidden:
        pass

    duration_str_log = f"{seconds//86400}d" if seconds>=86400 else f"{seconds//3600}h" if seconds>=3600 else f"{seconds//60}m" if seconds>=60 else f"{seconds}s"
    chatban_log.setdefault(member.id, []).append({"duration": duration_str_log, "reason": reason, "by": str(moderator), "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")})
    asyncio.create_task(_chatban_expire(guild, member, seconds))
    asyncio.create_task(send_review_panel(guild, member, seconds, reason, moderator))
    return embed

async def _chatban_expire(guild, member, seconds):
    await asyncio.sleep(seconds)
    for channel in guild.text_channels:
        try:
            await channel.set_permissions(member, send_messages=None,
                                          add_reactions=None,
                                          create_public_threads=None,
                                          create_private_threads=None,
                                          send_messages_in_threads=None, reason="Chat ban expired")
        except discord.Forbidden:
            pass
    try:
        await member.send(embed=success_embed("🔊  Chat Ban Lifted",
            f"Your chat ban in **{guild.name}** has expired. You can chat again!"))
    except discord.Forbidden:
        pass

# ════════════════════════════════════════════════════════════════════════════════
# PREFIX COMMANDS  (. prefix)
# ════════════════════════════════════════════════════════════════════════════════

# ── .chatban ──────────────────────────────────────────────────────────────────
@bot.command(name="chatban")
@commands.has_permissions(administrator=True)
async def chatban_prefix(ctx, user: discord.Member, duration: str, *, reason: str = "No reason provided"):
    seconds = parse_duration(duration)
    if not seconds:
        await ctx.reply("⚠️ Invalid duration. Examples: `30s` `10m` `2h` `1d`", delete_after=10); return
    if user.guild_permissions.administrator:
        await ctx.reply("⚠️ Can't chat-ban an administrator.", delete_after=10); return
    embed = await do_chatban(ctx.guild, user, seconds, reason, ctx.author)
    add_mod_log(user.id, "chatban", reason, str(ctx.author))
    await ctx.send(embed=embed)
    await ctx.message.delete()

# ── .unchatban ────────────────────────────────────────────────────────────────
@bot.command(name="unchatban")
@commands.has_permissions(administrator=True)
async def unchatban_prefix(ctx, user: discord.Member):
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(user, send_messages=None,
                                          add_reactions=None,
                                          create_public_threads=None,
                                          create_private_threads=None,
                                          send_messages_in_threads=None, reason=f"Unchatban by {ctx.author}")
        except discord.Forbidden:
            pass
    await ctx.send(embed=success_embed("🔊  Chat Ban Removed", f"{user.mention} can chat again."))
    await ctx.message.delete()

# ── .mute ─────────────────────────────────────────────────────────────────────
@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_prefix(ctx, user: discord.Member, duration: str, *, reason: str = "No reason provided"):
    seconds = parse_duration(duration)
    if not seconds:
        await ctx.reply("⚠️ Invalid duration.", delete_after=10); return
    if seconds > 2419200:
        await ctx.reply("⚠️ Max 28 days.", delete_after=10); return
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    await user.timeout(until, reason=f"{ctx.author}: {reason}")
    add_mod_log(user.id, "mute", reason, str(ctx.author))
    expiry_ts = int(until.timestamp())
    embed = discord.Embed(title="🔕  User Muted", color=0xFEE75C)
    embed.add_field(name="User",    value=user.mention, inline=False)
    embed.add_field(name="Expires", value=f"<t:{expiry_ts}:R>", inline=True)
    embed.add_field(name="Reason",  value=reason, inline=False)
    embed.add_field(name="By",      value=ctx.author.mention, inline=False)
    await ctx.send(embed=embed)
    await ctx.message.delete()
    try:
        await user.send(embed=discord.Embed(title="🔕  You've been muted",
            description=f"Muted in **{ctx.guild.name}**\n**Reason:** {reason}\n**Expires:** <t:{expiry_ts}:R>",
            color=0xFEE75C))
    except discord.Forbidden:
        pass

# ── .unmute ───────────────────────────────────────────────────────────────────
@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_prefix(ctx, user: discord.Member):
    await user.timeout(None, reason=f"Unmuted by {ctx.author}")
    await ctx.send(embed=success_embed("🔔  Unmuted", f"{user.mention} has been unmuted."))
    await ctx.message.delete()

# ── .kick ─────────────────────────────────────────────────────────────────────
@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_prefix(ctx, user: discord.Member, *, reason: str = "No reason provided"):
    if user.guild_permissions.administrator:
        await ctx.reply("⚠️ Can't kick an administrator.", delete_after=10); return
    try:
        await user.send(embed=discord.Embed(title="👢  Kicked",
            description=f"Kicked from **{ctx.guild.name}**\n**Reason:** {reason}", color=0xED4245))
    except discord.Forbidden:
        pass
    kick_log.setdefault(user.id, []).append({"reason": reason, "by": str(ctx.author), "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")})
    await user.kick(reason=f"{ctx.author}: {reason}")
    add_mod_log(user.id, "kick", reason, str(ctx.author))
    await ctx.send(embed=discord.Embed(title="👢  User Kicked",
        description=f"**{user}** kicked.\n**Reason:** {reason}\n**By:** {ctx.author.mention}", color=0xED4245))
    await ctx.message.delete()

# ── .ban ──────────────────────────────────────────────────────────────────────
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_prefix(ctx, user: discord.Member, *, reason: str = "No reason provided"):
    if user.guild_permissions.administrator:
        await ctx.reply("⚠️ Can't ban an administrator.", delete_after=10); return
    try:
        await user.send(embed=discord.Embed(title="🔨  Banned",
            description=f"Banned from **{ctx.guild.name}**\n**Reason:** {reason}", color=0xED4245))
    except discord.Forbidden:
        pass
    ban_log.setdefault(user.id, []).append({"reason": reason, "by": str(ctx.author), "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")})
    await user.ban(reason=f"{ctx.author}: {reason}")
    add_mod_log(user.id, "ban", reason, str(ctx.author))
    await ctx.send(embed=discord.Embed(title="🔨  User Banned",
        description=f"**{user}** banned.\n**Reason:** {reason}\n**By:** {ctx.author.mention}", color=0xED4245))
    await ctx.message.delete()

# ── .unban ────────────────────────────────────────────────────────────────────
@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_prefix(ctx, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(embed=success_embed("✅  Unbanned", f"**{user}** unbanned by {ctx.author.mention}."))
        await ctx.message.delete()
    except discord.NotFound:
        await ctx.reply("⚠️ User not found or not banned.", delete_after=10)

# ── .warn ─────────────────────────────────────────────────────────────────────
@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_prefix(ctx, user: discord.Member, *, reason: str = "No reason provided"):
    warnings.setdefault(user.id, []).append({
        "reason": reason, "by": str(ctx.author),
        "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    })
    count = len(warnings[user.id])
    await ctx.send(embed=discord.Embed(title="⚠️  User Warned", color=0xFEE75C,
        description=f"**User:** {user.mention}\n**Reason:** {reason}\n**By:** {ctx.author.mention}\n**Total warnings:** {count}"))
    await ctx.message.delete()
    try:
        await user.send(embed=discord.Embed(title="⚠️  Warning Received",
            description=f"Warned in **{ctx.guild.name}**\n**Reason:** {reason}\n**Total warnings:** {count}",
            color=0xFEE75C))
    except discord.Forbidden:
        pass
    await apply_warning_escalation(ctx.guild, user, count, ctx.channel)

# ── .warnings ─────────────────────────────────────────────────────────────────
@bot.command(name="warnings")
@commands.has_permissions(manage_messages=True)
async def warnings_prefix(ctx, user: discord.Member):
    user_warnings = warnings.get(user.id, [])
    if not user_warnings:
        await ctx.reply(f"✅ {user.mention} has no warnings.", delete_after=10); return
    embed = discord.Embed(title=f"⚠️  Warnings for {user}", description=f"Total: **{len(user_warnings)}**", color=0xFEE75C)
    for i, w in enumerate(user_warnings, 1):
        embed.add_field(name=f"#{i}", value=f"**Reason:** {w['reason']}\n**By:** {w['by']}\n**At:** {w['at']}", inline=False)
    await ctx.send(embed=embed)

# ── .clearwarnings ────────────────────────────────────────────────────────────
@bot.command(name="clearwarnings")
@commands.has_permissions(administrator=True)
async def clearwarnings_prefix(ctx, user: discord.Member):
    warnings.pop(user.id, None)
    await ctx.send(embed=success_embed("✅  Warnings Cleared", f"All warnings cleared for {user.mention}."))
    await ctx.message.delete()

# ── .purge ────────────────────────────────────────────────────────────────────
@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge_prefix(ctx, amount: int):
    if not 1 <= amount <= 100:
        await ctx.reply("⚠️ Between 1 and 100.", delete_after=10); return
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(embed=success_embed("🗑️  Purged", f"Deleted **{len(deleted)-1}** messages."), delete_after=5)

# ── .slowmode ─────────────────────────────────────────────────────────────────
@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode_prefix(ctx, seconds: int):
    if not 0 <= seconds <= 21600:
        await ctx.reply("⚠️ Between 0 and 21600 seconds.", delete_after=10); return
    await ctx.channel.edit(slowmode_delay=seconds)
    msg = "Slowmode disabled." if seconds == 0 else f"Slowmode set to **{seconds}s**."
    await ctx.send(embed=success_embed("✅  Slowmode", msg), delete_after=5)
    await ctx.message.delete()

# ── .modhelp ──────────────────────────────────────────────────────────────────
@bot.command(name="modhelp")
async def modhelp_prefix(ctx):
    embed = discord.Embed(title="🛡️  Moderation Commands", color=0x5865F2,
        description="Use `.command` or `/command`. You can **@mention** users or use their ID.")
    embed.add_field(name=".chatban @user [time] [reason]",  value="Remove chat perms temporarily", inline=False)
    embed.add_field(name=".unchatban @user",                value="Lift a chat ban early", inline=False)
    embed.add_field(name=".mute @user [time] [reason]",     value="Timeout a user", inline=False)
    embed.add_field(name=".unmute @user",                   value="Remove timeout", inline=False)
    embed.add_field(name=".kick @user [reason]",            value="Kick a user", inline=False)
    embed.add_field(name=".ban @user [reason]",             value="Ban a user", inline=False)
    embed.add_field(name=".unban [user_id]",                value="Unban a user", inline=False)
    embed.add_field(name=".warn @user [reason]",            value="Warn a user", inline=False)
    embed.add_field(name=".warnings @user",                 value="View warnings", inline=False)
    embed.add_field(name=".clearwarnings @user",            value="Clear warnings", inline=False)
    embed.add_field(name=".purge [amount]",                 value="Delete messages (max 100)", inline=False)
    embed.add_field(name=".slowmode [seconds]",             value="Set slowmode (0 to disable)", inline=False)
    embed.set_footer(text="Duration format: 30s / 10m / 2h / 1d")
    await ctx.send(embed=embed)

# ════════════════════════════════════════════════════════════════════════════════
# SLASH COMMANDS
# ════════════════════════════════════════════════════════════════════════════════

@tree.command(name="chatban", description="Remove a user's chat permissions for a duration")
@app_commands.describe(user="User to chat ban", duration="Duration e.g. 10m, 2h, 1d", reason="Reason for the ban")
@app_commands.default_permissions(administrator=True)
async def chatban_slash(interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = "No reason provided"):
    await interaction.response.defer(ephemeral=True)
    seconds = parse_duration(duration)
    if not seconds:
        await interaction.followup.send(embed=error_embed("Invalid duration. Examples: `30s` `10m` `2h` `1d`"), ephemeral=True); return
    if user.guild_permissions.administrator:
        await interaction.followup.send(embed=error_embed("Can't chat-ban an administrator."), ephemeral=True); return
    embed = await do_chatban(interaction.guild, user, seconds, reason, interaction.user)
    add_mod_log(user.id, "chatban", reason, str(interaction.user))
    await interaction.channel.send(embed=embed)
    await interaction.followup.send(embed=success_embed("✅  Done", f"{user.mention} has been chat banned."), ephemeral=True)

@tree.command(name="unchatban", description="Lift a user's chat ban early")
@app_commands.describe(user="User to unchat ban")
@app_commands.default_permissions(administrator=True)
async def unchatban_slash(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    for channel in interaction.guild.text_channels:
        try:
            await channel.set_permissions(user, send_messages=None,
                                          add_reactions=None,
                                          create_public_threads=None,
                                          create_private_threads=None,
                                          send_messages_in_threads=None, reason=f"Unchatban by {interaction.user}")
        except discord.Forbidden:
            pass
    await interaction.channel.send(embed=success_embed("🔊  Chat Ban Removed", f"{user.mention} can chat again."))
    await interaction.followup.send(embed=success_embed("✅  Done", "Chat ban lifted."), ephemeral=True)

@tree.command(name="mute", description="Timeout a user for a duration")
@app_commands.describe(user="User to mute", duration="Duration e.g. 10m, 2h", reason="Reason")
@app_commands.default_permissions(moderate_members=True)
async def mute_slash(interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = "No reason provided"):
    await interaction.response.defer(ephemeral=True)
    seconds = parse_duration(duration)
    if not seconds:
        await interaction.followup.send(embed=error_embed("Invalid duration."), ephemeral=True); return
    if seconds > 2419200:
        await interaction.followup.send(embed=error_embed("Max 28 days."), ephemeral=True); return
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    await user.timeout(until, reason=f"{interaction.user}: {reason}")
    add_mod_log(user.id, "mute", reason, str(interaction.user))
    expiry_ts = int(until.timestamp())
    embed = discord.Embed(title="🔕  User Muted", color=0xFEE75C,
        description=f"**User:** {user.mention}\n**Expires:** <t:{expiry_ts}:R>\n**Reason:** {reason}\n**By:** {interaction.user.mention}")
    await interaction.channel.send(embed=embed)
    await interaction.followup.send(embed=success_embed("✅  Done", f"{user.mention} muted."), ephemeral=True)

@tree.command(name="unmute", description="Remove a user's timeout")
@app_commands.describe(user="User to unmute")
@app_commands.default_permissions(moderate_members=True)
async def unmute_slash(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    await user.timeout(None, reason=f"Unmuted by {interaction.user}")
    await interaction.channel.send(embed=success_embed("🔔  Unmuted", f"{user.mention} unmuted by {interaction.user.mention}."))
    await interaction.followup.send(embed=success_embed("✅  Done", "User unmuted."), ephemeral=True)

@tree.command(name="kick", description="Kick a user from the server")
@app_commands.describe(user="User to kick", reason="Reason")
@app_commands.default_permissions(kick_members=True)
async def kick_slash(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer(ephemeral=True)
    if user.guild_permissions.administrator:
        await interaction.followup.send(embed=error_embed("Can't kick an administrator."), ephemeral=True); return
    try:
        await user.send(embed=discord.Embed(title="👢  Kicked",
            description=f"Kicked from **{interaction.guild.name}**\n**Reason:** {reason}", color=0xED4245))
    except discord.Forbidden:
        pass
    kick_log.setdefault(user.id, []).append({"reason": reason, "by": str(interaction.user), "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")})
    await user.kick(reason=f"{interaction.user}: {reason}")
    add_mod_log(user.id, "kick", reason, str(interaction.user))
    await interaction.channel.send(embed=discord.Embed(title="👢  User Kicked",
        description=f"**{user}** kicked.\n**Reason:** {reason}\n**By:** {interaction.user.mention}", color=0xED4245))
    await interaction.followup.send(embed=success_embed("✅  Done", "User kicked."), ephemeral=True)

@tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="User to ban", reason="Reason")
@app_commands.default_permissions(ban_members=True)
async def ban_slash(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer(ephemeral=True)
    if user.guild_permissions.administrator:
        await interaction.followup.send(embed=error_embed("Can't ban an administrator."), ephemeral=True); return
    try:
        await user.send(embed=discord.Embed(title="🔨  Banned",
            description=f"Banned from **{interaction.guild.name}**\n**Reason:** {reason}", color=0xED4245))
    except discord.Forbidden:
        pass
    ban_log.setdefault(user.id, []).append({"reason": reason, "by": str(interaction.user), "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")})
    await user.ban(reason=f"{interaction.user}: {reason}")
    add_mod_log(user.id, "ban", reason, str(interaction.user))
    await interaction.channel.send(embed=discord.Embed(title="🔨  User Banned",
        description=f"**{user}** banned.\n**Reason:** {reason}\n**By:** {interaction.user.mention}", color=0xED4245))
    await interaction.followup.send(embed=success_embed("✅  Done", "User banned."), ephemeral=True)

@tree.command(name="unban", description="Unban a user by their ID")
@app_commands.describe(user_id="The user's ID")
@app_commands.default_permissions(ban_members=True)
async def unban_slash(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer(ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.channel.send(embed=success_embed("✅  Unbanned", f"**{user}** unbanned by {interaction.user.mention}."))
        await interaction.followup.send(embed=success_embed("✅  Done", "User unbanned."), ephemeral=True)
    except discord.NotFound:
        await interaction.followup.send(embed=error_embed("User not found or not banned."), ephemeral=True)

@tree.command(name="warn", description="Warn a user")
@app_commands.describe(user="User to warn", reason="Reason")
@app_commands.default_permissions(manage_messages=True)
async def warn_slash(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    await interaction.response.defer(ephemeral=True)
    warnings.setdefault(user.id, []).append({
        "reason": reason, "by": str(interaction.user),
        "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    })
    count = len(warnings[user.id])
    await interaction.channel.send(embed=discord.Embed(title="⚠️  User Warned", color=0xFEE75C,
        description=f"**User:** {user.mention}\n**Reason:** {reason}\n**By:** {interaction.user.mention}\n**Total warnings:** {count}"))
    await interaction.followup.send(embed=success_embed("✅  Done", f"{user.mention} warned."), ephemeral=True)
    try:
        await user.send(embed=discord.Embed(title="⚠️  Warning Received",
            description=f"Warned in **{interaction.guild.name}**\n**Reason:** {reason}\n**Total warnings:** {count}", color=0xFEE75C))
    except discord.Forbidden:
        pass
    await apply_warning_escalation(interaction.guild, user, count, interaction.channel)

@tree.command(name="warnings", description="View warnings for a user")
@app_commands.describe(user="User to check")
@app_commands.default_permissions(manage_messages=True)
async def warnings_slash(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    user_warnings = warnings.get(user.id, [])
    if not user_warnings:
        await interaction.followup.send(embed=success_embed("✅  No Warnings", f"{user.mention} has no warnings."), ephemeral=True); return
    embed = discord.Embed(title=f"⚠️  Warnings for {user}", description=f"Total: **{len(user_warnings)}**", color=0xFEE75C)
    for i, w in enumerate(user_warnings, 1):
        embed.add_field(name=f"#{i}", value=f"**Reason:** {w['reason']}\n**By:** {w['by']}\n**At:** {w['at']}", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="clearwarnings", description="Clear all warnings for a user")
@app_commands.describe(user="User to clear warnings for")
@app_commands.default_permissions(administrator=True)
async def clearwarnings_slash(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    warnings.pop(user.id, None)
    await interaction.followup.send(embed=success_embed("✅  Cleared", f"All warnings cleared for {user.mention}."), ephemeral=True)

@tree.command(name="purge", description="Delete messages in this channel")
@app_commands.describe(amount="Number of messages to delete (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def purge_slash(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    if not 1 <= amount <= 100:
        await interaction.followup.send(embed=error_embed("Between 1 and 100."), ephemeral=True); return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(embed=success_embed("🗑️  Purged", f"Deleted **{len(deleted)}** messages."), ephemeral=True)

@tree.command(name="slowmode", description="Set slowmode for this channel")
@app_commands.describe(seconds="Seconds (0 to disable, max 21600)")
@app_commands.default_permissions(manage_channels=True)
async def slowmode_slash(interaction: discord.Interaction, seconds: int):
    await interaction.response.defer(ephemeral=True)
    if not 0 <= seconds <= 21600:
        await interaction.followup.send(embed=error_embed("Between 0 and 21600."), ephemeral=True); return
    await interaction.channel.edit(slowmode_delay=seconds)
    msg = "Slowmode disabled." if seconds == 0 else f"Slowmode set to **{seconds}s**."
    await interaction.followup.send(embed=success_embed("✅  Slowmode", msg), ephemeral=True)

@tree.command(name="modhelp", description="Show all moderation commands")
async def modhelp_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="🛡️  Moderation Commands", color=0x5865F2,
        description="Use `/command` or `.command` or `?command`. You can **@mention** users or use their ID.")
    embed.add_field(name="📋  General", value=(
        "`/usercheck @user` — View full mod history\n"
        "`/reviewpanel #channel` — Set chatban review channel"
    ), inline=False)
    embed.add_field(name="⚠️  Warnings & Bans", value=(
        "`/warn @user [reason]` — Warn a user\n"
        "`/warnings @user` — View warnings\n"
        "`/clearwarnings @user` — Clear all warnings\n"
        "`/chatban @user [time] [reason]` — Remove chat perms\n"
        "`/unchatban @user` — Lift chat ban early"
    ), inline=False)
    embed.add_field(name="🔨  Kicks & Bans", value=(
        "`/kick @user [reason]` — Kick a user\n"
        "`/ban @user [reason]` — Ban a user\n"
        "`/unban [user_id]` — Unban a user by ID"
    ), inline=False)
    embed.add_field(name="🔕  Timeouts & Cleanup", value=(
        "`/mute @user [time] [reason]` — Timeout a user\n"
        "`/unmute @user` — Remove timeout\n"
        "`/purge [amount]` — Delete messages (max 100)\n"
        "`/slowmode [seconds]` — Set slowmode (0 to disable)"
    ), inline=False)
    embed.add_field(name="📊  Auto Escalation", value=(
        "**3 warnings** → 1 day chat ban\n"
        "**5 warnings** → 1 week chat ban + final warning\n"
        "**6 warnings** → 1 month temp ban"
    ), inline=False)
    embed.set_footer(text="Duration format: 30s / 10m / 2h / 1d  •  Prefix: . or ?")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── .check ────────────────────────────────────────────────────────────────────
# In-memory logs for kicks and bans
kick_log: dict[int, list[dict]] = {}
ban_log: dict[int, list[dict]] = {}
chatban_log: dict[int, list[dict]] = {}

@bot.command(name="usercheck")
@commands.has_permissions(manage_messages=True)
async def usercheck_prefix(ctx, user: discord.Member):
    await _send_check(ctx.channel, user, ctx.guild)

@tree.command(name="usercheck", description="View full moderation history of a user")
@app_commands.describe(user="User to check")
@app_commands.default_permissions(manage_messages=True)
async def usercheck_slash(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    await _send_check(interaction.channel, user, interaction.guild)
    await interaction.followup.send(embed=success_embed("✅  Done", "Check sent to channel."), ephemeral=True)

async def _send_check(channel, member, guild):
    now = datetime.now(timezone.utc)

    # ── Account info
    created_at   = member.created_at
    joined_at    = member.joined_at
    account_age  = (now - created_at).days
    server_age   = (now - joined_at).days if joined_at else "N/A"

    # Flag potentially new accounts
    age_flag = "🚨 **New account — possible alt!**" if account_age < 30 else ""

    # ── Mod history from logs
    user_warnings  = warnings.get(member.id, [])
    user_chatbans  = chatban_log.get(member.id, [])
    user_kicks     = kick_log.get(member.id, [])
    user_bans      = ban_log.get(member.id, [])

    # ── Roles
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    roles_str = ", ".join(roles) if roles else "None"

    embed = discord.Embed(
        title=f"🔍  Moderation Check — {member}",
        color=0x5865F2,
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # Account info
    embed.add_field(
        name="👤  Account Info",
        value=(
            f"**ID:** `{member.id}`\n"
            f"**Created:** <t:{int(created_at.timestamp())}:D> ({account_age} days ago)\n"
            f"**Joined:** <t:{int(joined_at.timestamp())}:D> ({server_age} days ago)\n"
            f"**Roles:** {roles_str}\n"
            f"{age_flag}"
        ),
        inline=False,
    )

    # Summary
    embed.add_field(
        name="📊  Moderation Summary",
        value=(
            f"⚠️ **Warnings:** {len(user_warnings)}\n"
            f"🔇 **Chat Bans:** {len(user_chatbans)}\n"
            f"👢 **Kicks:** {len(user_kicks)}\n"
            f"🔨 **Bans:** {len(user_bans)}"
        ),
        inline=False,
    )

    # Warnings detail
    if user_warnings:
        val = "\n".join([f"`#{i+1}` {w['reason']} — by {w['by']} ({w['at']})" for i, w in enumerate(user_warnings[-5:])])
        if len(user_warnings) > 5:
            val += f"\n*...and {len(user_warnings)-5} more*"
        embed.add_field(name=f"⚠️  Warnings ({len(user_warnings)})", value=val, inline=False)

    # Chat bans detail
    if user_chatbans:
        val = "\n".join([f"`#{i+1}` {c['duration']} — {c['reason']} — by {c['by']} ({c['at']})" for i, c in enumerate(user_chatbans[-3:])])
        embed.add_field(name=f"🔇  Chat Bans ({len(user_chatbans)})", value=val, inline=False)

    # Kicks detail
    if user_kicks:
        val = "\n".join([f"`#{i+1}` {k['reason']} — by {k['by']} ({k['at']})" for i, k in enumerate(user_kicks[-3:])])
        embed.add_field(name=f"👢  Kicks ({len(user_kicks)})", value=val, inline=False)

    # Bans detail
    if user_bans:
        val = "\n".join([f"`#{i+1}` {b['reason']} — by {b['by']} ({b['at']})" for i, b in enumerate(user_bans[-3:])])
        embed.add_field(name=f"🔨  Bans ({len(user_bans)})", value=val, inline=False)

    if not any([user_warnings, user_chatbans, user_kicks, user_bans]):
        embed.add_field(name="✅  Clean Record", value="No moderation actions on record.", inline=False)

    embed.set_footer(text=f"Checked by moderator • {now.strftime('%d %b %Y %H:%M UTC')}")
    await channel.send(embed=embed)


# ── Mod log store ─────────────────────────────────────────────────────────────
mod_log: dict[int, list[dict]] = {}

def add_mod_log(user_id: int, action: str, reason: str, moderator: str):
    mod_log.setdefault(user_id, []).append({
        "action": action,
        "reason": reason,
        "by": moderator,
        "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    })

# ── .check ────────────────────────────────────────────────────────────────────
async def send_check_embed(send_fn, member: discord.Member, guild: discord.Guild, **kwargs):
    user_warnings = warnings.get(member.id, [])
    user_logs     = mod_log.get(member.id, [])

    kicks     = [e for e in user_logs if e["action"] == "kick"]
    bans      = [e for e in user_logs if e["action"] == "ban"]
    chatbans  = [e for e in user_logs if e["action"] == "chatban"]
    mutes     = [e for e in user_logs if e["action"] == "mute"]

    # Account age
    created_at = member.created_at.strftime("%d %b %Y")
    joined_at  = member.joined_at.strftime("%d %b %Y") if member.joined_at else "Unknown"
    account_age_days = (datetime.now(timezone.utc) - member.created_at).days

    # Alt detection heuristic: account < 30 days old
    alt_warning = ""
    if account_age_days < 30:
        alt_warning = f"\n⚠️ **Possible alt** — account is only **{account_age_days} days old**"

    embed = discord.Embed(
        title=f"🔍  Moderation Profile — {member}",
        color=0xED4245 if (user_warnings or kicks or bans) else 0x57F287,
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # ── Account info
    embed.add_field(
        name="👤  Account Info",
        value=(
            f"**ID:** `{member.id}`\n"
            f"**Created:** {created_at} ({account_age_days} days ago)\n"
            f"**Joined:** {joined_at}\n"
            f"**Roles:** {len(member.roles) - 1}"
            f"{alt_warning}"
        ),
        inline=False,
    )

    # ── Summary
    embed.add_field(
        name="📊  Moderation Summary",
        value=(
            f"⚠️ **Warnings:** {len(user_warnings)}\n"
            f"🔇 **Chat Bans:** {len(chatbans)}\n"
            f"🔕 **Mutes:** {len(mutes)}\n"
            f"👢 **Kicks:** {len(kicks)}\n"
            f"🔨 **Bans:** {len(bans)}"
        ),
        inline=False,
    )

    # ── Warnings detail
    if user_warnings:
        warn_text = ""
        for i, w in enumerate(user_warnings[-5:], 1):
            warn_text += f"**#{i}** {w['reason']} — by {w['by']} ({w['at']})\n"
        if len(user_warnings) > 5:
            warn_text += f"_...and {len(user_warnings) - 5} more_"
        embed.add_field(name="⚠️  Recent Warnings", value=warn_text, inline=False)

    # ── Action history
    if user_logs:
        log_text = ""
        for e in reversed(user_logs[-8:]):
            icon = {"kick": "👢", "ban": "🔨", "chatban": "🔇", "mute": "🔕"}.get(e["action"], "📋")
            log_text += f"{icon} **{e['action'].capitalize()}** — {e['reason']} — by {e['by']} ({e['at']})\n"
        if len(user_logs) > 8:
            log_text += f"_...and {len(user_logs) - 8} more_"
        embed.add_field(name="📋  Action History", value=log_text, inline=False)

    # ── Notes
    user_notes = mod_notes.get(member.id, [])
    if user_notes:
        notes_text = ""
        for i, n in enumerate(user_notes[-3:], 1):
            notes_text += f"**{n['note']}** — {n['by']} ({n['at']})\n"
        if len(user_notes) > 3:
            notes_text += f"_...and {len(user_notes) - 3} more_"
        embed.add_field(name="📝  Moderator Notes", value=notes_text, inline=False)

    if not user_warnings and not user_logs:
        embed.add_field(name="✅  Clean Record", value="No moderation actions on record.", inline=False)

    embed.set_footer(text=f"Requested by a moderator • {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}")
    await send_fn(embed=embed, **kwargs)



# ── Mod notes store ───────────────────────────────────────────────────────────
mod_notes: dict[int, list[dict]] = {}
word_filter: set[str] = set()

# ── .lock / .unlock ───────────────────────────────────────────────────────────
@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=False,
                                   reason=f"Channel locked by {ctx.author}")
    await ctx.send(embed=success_embed("🔒  Channel Locked", f"{channel.mention} has been locked."))
    await ctx.message.delete()

@tree.command(name="lock", description="Lock a channel")
@app_commands.describe(channel="Channel to lock (current channel if not specified)")
@app_commands.default_permissions(manage_channels=True)
async def lock_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False,
                                   reason=f"Channel locked by {interaction.user}")
    await interaction.response.send_message(
        embed=success_embed("🔒  Channel Locked", f"{channel.mention} has been locked."),
        ephemeral=True
    )

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=None,
                                   reason=f"Channel unlocked by {ctx.author}")
    await ctx.send(embed=success_embed("🔓  Channel Unlocked", f"{channel.mention} has been unlocked."))
    await ctx.message.delete()

@tree.command(name="unlock", description="Unlock a channel")
@app_commands.describe(channel="Channel to unlock")
@app_commands.default_permissions(manage_channels=True)
async def unlock_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=None,
                                   reason=f"Channel unlocked by {interaction.user}")
    await interaction.response.send_message(
        embed=success_embed("🔓  Channel Unlocked", f"{channel.mention} has been unlocked."),
        ephemeral=True
    )

# ── .lockdown ─────────────────────────────────────────────────────────────────
@bot.command(name="lockdown")
@commands.has_permissions(administrator=True)
async def lockdown_prefix(ctx):
    await ctx.send(embed=discord.Embed(description="🔒  Locking down all channels…", color=0xFEE75C))
    locked = 0
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=False,
                                          reason=f"Server lockdown by {ctx.author}")
            locked += 1
        except discord.Forbidden:
            pass
    await ctx.send(embed=success_embed("🔒  Server Lockdown", f"Locked **{locked}** channels."))
    await ctx.message.delete()

@tree.command(name="lockdown", description="Lock all channels in the server")
@app_commands.default_permissions(administrator=True)
async def lockdown_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    locked = 0
    for channel in interaction.guild.text_channels:
        try:
            await channel.set_permissions(interaction.guild.default_role, send_messages=False,
                                          reason=f"Server lockdown by {interaction.user}")
            locked += 1
        except discord.Forbidden:
            pass
    await interaction.channel.send(embed=success_embed("🔒  Server Lockdown", f"Locked **{locked}** channels by {interaction.user.mention}."))
    await interaction.followup.send(embed=success_embed("✅  Done", f"Locked {locked} channels."), ephemeral=True)

# ── .nuke ─────────────────────────────────────────────────────────────────────
@bot.command(name="nuke")
@commands.has_permissions(manage_channels=True)
async def nuke_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    position = channel.position
    new_channel = await channel.clone(reason=f"Channel nuked by {ctx.author}")
    await new_channel.edit(position=position)
    await channel.delete(reason=f"Channel nuked by {ctx.author}")
    await new_channel.send(embed=success_embed("💥  Channel Nuked", f"This channel was nuked by {ctx.author.mention}."))

@tree.command(name="nuke", description="Clone and delete a channel (clears all messages)")
@app_commands.describe(channel="Channel to nuke")
@app_commands.default_permissions(manage_channels=True)
async def nuke_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)
    channel = channel or interaction.channel
    position = channel.position
    new_channel = await channel.clone(reason=f"Channel nuked by {interaction.user}")
    await new_channel.edit(position=position)
    await channel.delete(reason=f"Channel nuked by {interaction.user}")
    await new_channel.send(embed=success_embed("💥  Channel Nuked", f"This channel was nuked by {interaction.user.mention}."))

# ── .nickname ─────────────────────────────────────────────────────────────────
@bot.command(name="nickname")
@commands.has_permissions(manage_nicknames=True)
async def nickname_prefix(ctx, user: discord.Member, *, nickname: str = None):
    old_nick = user.display_name
    await user.edit(nick=nickname, reason=f"Nickname changed by {ctx.author}")
    new_text = f"`{nickname}`" if nickname else "removed"
    await ctx.send(embed=success_embed("✏️  Nickname Changed", 
        f"{user.mention}'s nickname changed from `{old_nick}` to {new_text}."))
    await ctx.message.delete()

@tree.command(name="nickname", description="Change a user's nickname")
@app_commands.describe(user="User to rename", nickname="New nickname (leave empty to reset)")
@app_commands.default_permissions(manage_nicknames=True)
async def nickname_slash(interaction: discord.Interaction, user: discord.Member, nickname: str = None):
    old_nick = user.display_name
    await user.edit(nick=nickname, reason=f"Nickname changed by {interaction.user}")
    new_text = f"`{nickname}`" if nickname else "removed"
    await interaction.response.send_message(
        embed=success_embed("✏️  Nickname Changed", f"{user.mention}: `{old_nick}` → {new_text}"),
        ephemeral=True
    )

# ── .role ─────────────────────────────────────────────────────────────────────
@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role_prefix(ctx, user: discord.Member, role: discord.Role):
    if role in user.roles:
        await user.remove_roles(role, reason=f"Role removed by {ctx.author}")
        await ctx.send(embed=success_embed("➖  Role Removed", f"Removed {role.mention} from {user.mention}."))
    else:
        await user.add_roles(role, reason=f"Role added by {ctx.author}")
        await ctx.send(embed=success_embed("➕  Role Added", f"Added {role.mention} to {user.mention}."))
    await ctx.message.delete()

@tree.command(name="role", description="Add or remove a role from a user")
@app_commands.describe(user="User", role="Role to add/remove")
@app_commands.default_permissions(manage_roles=True)
async def role_slash(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if role in user.roles:
        await user.remove_roles(role, reason=f"Role removed by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed("➖  Role Removed", f"Removed {role.mention} from {user.mention}."),
            ephemeral=True
        )
    else:
        await user.add_roles(role, reason=f"Role added by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed("➕  Role Added", f"Added {role.mention} to {user.mention}."),
            ephemeral=True
        )

# ── .note ─────────────────────────────────────────────────────────────────────
@bot.command(name="note")
@commands.has_permissions(manage_messages=True)
async def note_prefix(ctx, user: discord.Member, *, note: str):
    mod_notes.setdefault(user.id, []).append({
        "note": note,
        "by": str(ctx.author),
        "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    })
    await ctx.send(embed=success_embed("📝  Note Added", f"Added a private note for {user.mention}."))
    await ctx.message.delete()

@tree.command(name="note", description="Add a private moderator note about a user")
@app_commands.describe(user="User", note="Note text")
@app_commands.default_permissions(manage_messages=True)
async def note_slash(interaction: discord.Interaction, user: discord.Member, note: str):
    mod_notes.setdefault(user.id, []).append({
        "note": note,
        "by": str(interaction.user),
        "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    })
    await interaction.response.send_message(
        embed=success_embed("📝  Note Added", f"Added a private note for {user.mention}."),
        ephemeral=True
    )

@bot.command(name="notes")
@commands.has_permissions(manage_messages=True)
async def notes_prefix(ctx, user: discord.Member):
    user_notes = mod_notes.get(user.id, [])
    if not user_notes:
        await ctx.reply(f"📝 No notes for {user.mention}.", delete_after=10)
        return
    embed = discord.Embed(title=f"📝  Notes for {user}", color=0x5865F2)
    for i, n in enumerate(user_notes, 1):
        embed.add_field(name=f"Note #{i}", value=f"{n['note']}\n— {n['by']} ({n['at']})", inline=False)
    await ctx.send(embed=embed)

@tree.command(name="notes", description="View all moderator notes for a user")
@app_commands.describe(user="User")
@app_commands.default_permissions(manage_messages=True)
async def notes_slash(interaction: discord.Interaction, user: discord.Member):
    user_notes = mod_notes.get(user.id, [])
    if not user_notes:
        await interaction.response.send_message(
            embed=discord.Embed(description=f"📝 No notes for {user.mention}.", color=0x5865F2),
            ephemeral=True
        )
        return
    embed = discord.Embed(title=f"📝  Notes for {user}", color=0x5865F2)
    for i, n in enumerate(user_notes, 1):
        embed.add_field(name=f"Note #{i}", value=f"{n['note']}\n— {n['by']} ({n['at']})", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── .filter ───────────────────────────────────────────────────────────────────
@bot.command(name="filter")
@commands.has_permissions(manage_messages=True)
async def filter_prefix(ctx, action: str, *, word: str = None):
    if action.lower() == "add" and word:
        word_filter.add(word.lower())
        await ctx.send(embed=success_embed("🚫  Word Added", f"`{word}` added to the filter."))
    elif action.lower() == "remove" and word:
        word_filter.discard(word.lower())
        await ctx.send(embed=success_embed("✅  Word Removed", f"`{word}` removed from the filter."))
    elif action.lower() == "list":
        if not word_filter:
            await ctx.reply("🚫 No filtered words.", delete_after=10)
        else:
            await ctx.send(embed=discord.Embed(
                title="🚫  Filtered Words",
                description=", ".join(f"`{w}`" for w in sorted(word_filter)),
                color=0xED4245
            ))
    else:
        await ctx.reply("Usage: `.filter add/remove/list [word]`", delete_after=10)
    await ctx.message.delete()

@tree.command(name="filter", description="Manage the word filter")
@app_commands.describe(action="Action: add, remove, or list", word="Word to add/remove")
@app_commands.default_permissions(manage_messages=True)
async def filter_slash(interaction: discord.Interaction, action: str, word: str = None):
    if action.lower() == "add" and word:
        word_filter.add(word.lower())
        await interaction.response.send_message(
            embed=success_embed("🚫  Word Added", f"`{word}` added to the filter."),
            ephemeral=True
        )
    elif action.lower() == "remove" and word:
        word_filter.discard(word.lower())
        await interaction.response.send_message(
            embed=success_embed("✅  Word Removed", f"`{word}` removed from the filter."),
            ephemeral=True
        )
    elif action.lower() == "list":
        if not word_filter:
            await interaction.response.send_message(
                embed=discord.Embed(description="🚫 No filtered words.", color=0x5865F2),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=discord.Embed(
                title="🚫  Filtered Words",
                description=", ".join(f"`{w}`" for w in sorted(word_filter)),
                color=0xED4245
            ), ephemeral=True)

# ── Word filter listener ──────────────────────────────────────────────────────
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    
    # Check word filter
    if word_filter and any(word in message.content.lower() for word in word_filter):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} your message was deleted (filtered word).",
                delete_after=5
            )
        except discord.Forbidden:
            pass
    
    await bot.process_commands(message)

# ── .avatar ───────────────────────────────────────────────────────────────────
@bot.command(name="avatar")
async def avatar_prefix(ctx, user: discord.Member = None):
    user = user or ctx.author
    embed = discord.Embed(title=f"{user}'s Avatar", color=0x5865F2)
    embed.set_image(url=user.display_avatar.url)
    await ctx.send(embed=embed)

@tree.command(name="avatar", description="Show a user's avatar")
@app_commands.describe(user="User (defaults to you)")
async def avatar_slash(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user}'s Avatar", color=0x5865F2)
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# ── .serverinfo ───────────────────────────────────────────────────────────────
@bot.command(name="serverinfo")
async def serverinfo_prefix(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"📊  {guild.name}", color=0x5865F2)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="👑  Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="👥  Members", value=guild.member_count, inline=True)
    embed.add_field(name="📅  Created", value=guild.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field(name="💬  Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭  Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="😀  Emojis", value=len(guild.emojis), inline=True)
    await ctx.send(embed=embed)

@tree.command(name="serverinfo", description="Show server information")
async def serverinfo_slash(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"📊  {guild.name}", color=0x5865F2)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="👑  Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="👥  Members", value=guild.member_count, inline=True)
    embed.add_field(name="📅  Created", value=guild.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field(name="💬  Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭  Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="😀  Emojis", value=len(guild.emojis), inline=True)
    await interaction.response.send_message(embed=embed)


# ── .lock / .unlock ───────────────────────────────────────────────────────────
@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(embed=success_embed("🔒  Channel Locked", f"{channel.mention} is now locked."))

@tree.command(name="lock", description="Lock a channel")
@app_commands.describe(channel="Channel to lock (defaults to current)")
@app_commands.default_permissions(manage_channels=True)
async def lock_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message(
        embed=success_embed("🔒  Channel Locked", f"{channel.mention} is now locked."), ephemeral=True
    )

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=None)
    await ctx.send(embed=success_embed("🔓  Channel Unlocked", f"{channel.mention} is now unlocked."))

@tree.command(name="unlock", description="Unlock a channel")
@app_commands.describe(channel="Channel to unlock (defaults to current)")
@app_commands.default_permissions(manage_channels=True)
async def unlock_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=None)
    await interaction.response.send_message(
        embed=success_embed("🔓  Channel Unlocked", f"{channel.mention} is now unlocked."), ephemeral=True
    )

# ── .lockdown ─────────────────────────────────────────────────────────────────
@bot.command(name="lockdown")
@commands.has_permissions(administrator=True)
async def lockdown_prefix(ctx):
    await ctx.send(embed=discord.Embed(description="⏳  Locking down all channels...", color=0xFEE75C))
    locked = 0
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=False)
            locked += 1
        except discord.Forbidden:
            pass
    await ctx.send(embed=success_embed("🔒  Server Lockdown", f"Locked {locked} channels."))

@tree.command(name="lockdown", description="Lock all channels in the server")
@app_commands.default_permissions(administrator=True)
async def lockdown_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    locked = 0
    for channel in interaction.guild.text_channels:
        try:
            await channel.set_permissions(interaction.guild.default_role, send_messages=False)
            locked += 1
        except discord.Forbidden:
            pass
    await interaction.followup.send(embed=success_embed("🔒  Server Lockdown", f"Locked {locked} channels."), ephemeral=True)

# ── .nuke ─────────────────────────────────────────────────────────────────────
@bot.command(name="nuke")
@commands.has_permissions(manage_channels=True)
async def nuke_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    position = channel.position
    new_channel = await channel.clone(reason=f"Nuked by {ctx.author}")
    await channel.delete()
    await new_channel.edit(position=position)
    await new_channel.send(embed=success_embed("💥  Channel Nuked", f"This channel was nuked by {ctx.author.mention}."))

@tree.command(name="nuke", description="Clone and delete a channel (clears all messages)")
@app_commands.describe(channel="Channel to nuke (defaults to current)")
@app_commands.default_permissions(manage_channels=True)
async def nuke_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    position = channel.position
    await interaction.response.send_message(embed=discord.Embed(description="💥  Nuking channel...", color=0xFEE75C), ephemeral=True)
    new_channel = await channel.clone(reason=f"Nuked by {interaction.user}")
    await channel.delete()
    await new_channel.edit(position=position)
    await new_channel.send(embed=success_embed("💥  Channel Nuked", f"This channel was nuked by {interaction.user.mention}."))

# ── .nickname ─────────────────────────────────────────────────────────────────
@bot.command(name="nickname")
@commands.has_permissions(manage_nicknames=True)
async def nickname_prefix(ctx, user: discord.Member, *, nickname: str):
    old_nick = user.display_name
    await user.edit(nick=nickname, reason=f"Nickname changed by {ctx.author}")
    await ctx.send(embed=success_embed("✏️  Nickname Changed", f"{user.mention}: `{old_nick}` → `{nickname}`"))
    await ctx.message.delete()

@tree.command(name="nickname", description="Change a user's nickname")
@app_commands.describe(user="User to rename", nickname="New nickname")
@app_commands.default_permissions(manage_nicknames=True)
async def nickname_slash(interaction: discord.Interaction, user: discord.Member, nickname: str):
    old_nick = user.display_name
    await user.edit(nick=nickname, reason=f"Nickname changed by {interaction.user}")
    await interaction.response.send_message(
        embed=success_embed("✏️  Nickname Changed", f"{user.mention}: `{old_nick}` → `{nickname}`"), ephemeral=True
    )

# ── .role ─────────────────────────────────────────────────────────────────────
@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role_prefix(ctx, user: discord.Member, role: discord.Role):
    if role in user.roles:
        await user.remove_roles(role, reason=f"Role removed by {ctx.author}")
        await ctx.send(embed=success_embed("➖  Role Removed", f"Removed {role.mention} from {user.mention}."))
    else:
        await user.add_roles(role, reason=f"Role added by {ctx.author}")
        await ctx.send(embed=success_embed("➕  Role Added", f"Added {role.mention} to {user.mention}."))
    await ctx.message.delete()

@tree.command(name="role", description="Add or remove a role from a user")
@app_commands.describe(user="User to modify", role="Role to add/remove")
@app_commands.default_permissions(manage_roles=True)
async def role_slash(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if role in user.roles:
        await user.remove_roles(role, reason=f"Role removed by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed("➖  Role Removed", f"Removed {role.mention} from {user.mention}."), ephemeral=True
        )
    else:
        await user.add_roles(role, reason=f"Role added by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed("➕  Role Added", f"Added {role.mention} to {user.mention}."), ephemeral=True
        )

# ── .note ─────────────────────────────────────────────────────────────────────
@bot.command(name="note")
@commands.has_permissions(manage_messages=True)
async def note_prefix(ctx, user: discord.Member, *, note: str):
    mod_notes.setdefault(user.id, []).append(f"[{datetime.now(timezone.utc).strftime('%d %b %H:%M')}] {ctx.author}: {note}")
    await ctx.send(embed=success_embed("📝  Note Added", f"Added note for {user.mention}."))
    await ctx.message.delete()

@tree.command(name="note", description="Add a private moderator note about a user")
@app_commands.describe(user="User to note", note="Note content")
@app_commands.default_permissions(manage_messages=True)
async def note_slash(interaction: discord.Interaction, user: discord.Member, note: str):
    mod_notes.setdefault(user.id, []).append(f"[{datetime.now(timezone.utc).strftime('%d %b %H:%M')}] {interaction.user}: {note}")
    await interaction.response.send_message(embed=success_embed("📝  Note Added", f"Added note for {user.mention}."), ephemeral=True)

@bot.command(name="notes")
@commands.has_permissions(manage_messages=True)
async def notes_prefix(ctx, user: discord.Member):
    user_notes = mod_notes.get(user.id, [])
    if not user_notes:
        await ctx.reply(f"📝 No notes for {user.mention}.", delete_after=10)
        return
    embed = discord.Embed(title=f"📝  Mod Notes — {user}", color=0xFEE75C)
    for i, note in enumerate(user_notes, 1):
        embed.add_field(name=f"Note #{i}", value=note, inline=False)
    await ctx.send(embed=embed)

@tree.command(name="notes", description="View all moderator notes for a user")
@app_commands.describe(user="User to check notes for")
@app_commands.default_permissions(manage_messages=True)
async def notes_slash(interaction: discord.Interaction, user: discord.Member):
    user_notes = mod_notes.get(user.id, [])
    if not user_notes:
        await interaction.response.send_message(f"📝 No notes for {user.mention}.", ephemeral=True)
        return
    embed = discord.Embed(title=f"📝  Mod Notes — {user}", color=0xFEE75C)
    for i, note in enumerate(user_notes, 1):
        embed.add_field(name=f"Note #{i}", value=note, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── .filter ───────────────────────────────────────────────────────────────────
@bot.command(name="filter")
@commands.has_permissions(manage_messages=True)
async def filter_prefix(ctx, action: str, *, word: str = None):
    if action.lower() == "add" and word:
        filtered_words.add(word.lower())
        await ctx.send(embed=success_embed("🚫  Word Filtered", f"Added `{word}` to filter."))
    elif action.lower() == "remove" and word:
        filtered_words.discard(word.lower())
        await ctx.send(embed=success_embed("✅  Word Unfiltered", f"Removed `{word}` from filter."))
    elif action.lower() == "list":
        if not filtered_words:
            await ctx.reply("No filtered words.", delete_after=10)
            return
        await ctx.send(embed=discord.Embed(title="🚫  Filtered Words", description="\n".join(f"`{w}`" for w in filtered_words), color=0xED4245))
    else:
        await ctx.reply("Usage: `.filter add/remove/list [word]`", delete_after=10)
    await ctx.message.delete()

@tree.command(name="filter", description="Manage word filter")
@app_commands.describe(action="add/remove/list", word="Word to filter")
@app_commands.default_permissions(manage_messages=True)
async def filter_slash(interaction: discord.Interaction, action: str, word: str = None):
    if action.lower() == "add" and word:
        filtered_words.add(word.lower())
        await interaction.response.send_message(embed=success_embed("🚫  Word Filtered", f"Added `{word}` to filter."), ephemeral=True)
    elif action.lower() == "remove" and word:
        filtered_words.discard(word.lower())
        await interaction.response.send_message(embed=success_embed("✅  Word Unfiltered", f"Removed `{word}` from filter."), ephemeral=True)
    elif action.lower() == "list":
        if not filtered_words:
            await interaction.response.send_message("No filtered words.", ephemeral=True)
            return
        await interaction.response.send_message(embed=discord.Embed(title="🚫  Filtered Words", description="\n".join(f"`{w}`" for w in filtered_words), color=0xED4245), ephemeral=True)
    else:
        await interaction.response.send_message("Usage: `/filter add/remove/list [word]`", ephemeral=True)

# ── .avatar ───────────────────────────────────────────────────────────────────
@bot.command(name="avatar")
async def avatar_prefix(ctx, user: discord.Member = None):
    user = user or ctx.author
    embed = discord.Embed(title=f"🖼️  {user}'s Avatar", color=0x5865F2)
    embed.set_image(url=user.display_avatar.url)
    await ctx.send(embed=embed)

@tree.command(name="avatar", description="Show a user's avatar")
@app_commands.describe(user="User to view (defaults to you)")
async def avatar_slash(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"🖼️  {user}'s Avatar", color=0x5865F2)
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── .serverinfo ───────────────────────────────────────────────────────────────
@bot.command(name="serverinfo")
async def serverinfo_prefix(ctx):
    g = ctx.guild
    embed = discord.Embed(title=f"ℹ️  {g.name}", color=0x5865F2)
    embed.set_thumbnail(url=g.icon.url if g.icon else None)
    embed.add_field(name="👑  Owner", value=g.owner.mention, inline=True)
    embed.add_field(name="📅  Created", value=g.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field(name="👥  Members", value=g.member_count, inline=True)
    embed.add_field(name="💬  Channels", value=len(g.channels), inline=True)
    embed.add_field(name="🎭  Roles", value=len(g.roles), inline=True)
    embed.add_field(name="😀  Emojis", value=len(g.emojis), inline=True)
    await ctx.send(embed=embed)

@tree.command(name="serverinfo", description="Show server information")
async def serverinfo_slash(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"ℹ️  {g.name}", color=0x5865F2)
    embed.set_thumbnail(url=g.icon.url if g.icon else None)
    embed.add_field(name="👑  Owner", value=g.owner.mention, inline=True)
    embed.add_field(name="📅  Created", value=g.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field(name="👥  Members", value=g.member_count, inline=True)
    embed.add_field(name="💬  Channels", value=len(g.channels), inline=True)
    embed.add_field(name="🎭  Roles", value=len(g.roles), inline=True)
    embed.add_field(name="😀  Emojis", value=len(g.emojis), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── Auto-filter on message ────────────────────────────────────────────────────
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    if await check_spam(message):
        return
    if filtered_words and any(word in message.content.lower() for word in filtered_words):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} your message contained a filtered word.", delete_after=5
            )
        except discord.Forbidden:
            pass
    await bot.process_commands(message)



# ── .lock / .unlock ───────────────────────────────────────────────────────────
@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(embed=success_embed("🔒  Channel Locked", f"{channel.mention} is now locked."))

@tree.command(name="lock", description="Lock a channel so only mods can talk")
@app_commands.describe(channel="Channel to lock (default: current channel)")
@app_commands.default_permissions(manage_channels=True)
async def lock_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message(
        embed=success_embed("🔒  Channel Locked", f"{channel.mention} is now locked."),
        ephemeral=True
    )

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=None)
    await ctx.send(embed=success_embed("🔓  Channel Unlocked", f"{channel.mention} is now unlocked."))

@tree.command(name="unlock", description="Unlock a previously locked channel")
@app_commands.describe(channel="Channel to unlock (default: current channel)")
@app_commands.default_permissions(manage_channels=True)
async def unlock_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=None)
    await interaction.response.send_message(
        embed=success_embed("🔓  Channel Unlocked", f"{channel.mention} is now unlocked."),
        ephemeral=True
    )

# ── .lockdown ─────────────────────────────────────────────────────────────────
@bot.command(name="lockdown")
@commands.has_permissions(administrator=True)
async def lockdown_prefix(ctx):
    await ctx.send(embed=discord.Embed(description="🔒 Locking down all channels...", color=0xFEE75C))
    for channel in ctx.guild.text_channels:
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=False)
        except:
            pass
    await ctx.send(embed=success_embed("🔒  Server Locked Down", "All channels have been locked."))

@tree.command(name="lockdown", description="Lock down all channels in the server")
@app_commands.default_permissions(administrator=True)
async def lockdown_slash(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=discord.Embed(description="🔒 Locking down all channels...", color=0xFEE75C),
        ephemeral=True
    )
    for channel in interaction.guild.text_channels:
        try:
            await channel.set_permissions(interaction.guild.default_role, send_messages=False)
        except:
            pass
    await interaction.followup.send(embed=success_embed("🔒  Server Locked Down", "All channels locked."), ephemeral=True)

# ── .nuke ─────────────────────────────────────────────────────────────────────
@bot.command(name="nuke")
@commands.has_permissions(manage_channels=True)
async def nuke_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    pos = channel.position
    new_channel = await channel.clone(reason=f"Nuked by {ctx.author}")
    await channel.delete()
    await new_channel.edit(position=pos)
    await new_channel.send(embed=success_embed("💥  Channel Nuked", f"Channel cleared by {ctx.author.mention}."))

@tree.command(name="nuke", description="Clone a channel and delete the original (clears all messages)")
@app_commands.describe(channel="Channel to nuke (default: current channel)")
@app_commands.default_permissions(manage_channels=True)
async def nuke_slash(interaction: discord.Interaction, channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    pos = channel.position
    await interaction.response.send_message(embed=discord.Embed(description="💥 Nuking channel...", color=0xFEE75C), ephemeral=True)
    new_channel = await channel.clone(reason=f"Nuked by {interaction.user}")
    await channel.delete()
    await new_channel.edit(position=pos)
    await new_channel.send(embed=success_embed("💥  Channel Nuked", f"Channel cleared by {interaction.user.mention}."))

# ── .nickname ─────────────────────────────────────────────────────────────────
@bot.command(name="nickname")
@commands.has_permissions(manage_nicknames=True)
async def nickname_prefix(ctx, user: discord.Member, *, nickname: str = None):
    old_nick = user.display_name
    await user.edit(nick=nickname, reason=f"Nickname changed by {ctx.author}")
    new_nick = nickname or user.name
    await ctx.send(embed=success_embed("✏️  Nickname Changed", f"{user.mention}: `{old_nick}` → `{new_nick}`"))
    await ctx.message.delete()

@tree.command(name="nickname", description="Change a user's nickname")
@app_commands.describe(user="User to rename", nickname="New nickname (leave empty to reset)")
@app_commands.default_permissions(manage_nicknames=True)
async def nickname_slash(interaction: discord.Interaction, user: discord.Member, nickname: str = None):
    old_nick = user.display_name
    await user.edit(nick=nickname, reason=f"Nickname changed by {interaction.user}")
    new_nick = nickname or user.name
    await interaction.response.send_message(
        embed=success_embed("✏️  Nickname Changed", f"{user.mention}: `{old_nick}` → `{new_nick}`"),
        ephemeral=True
    )

# ── .role ─────────────────────────────────────────────────────────────────────
@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def role_prefix(ctx, user: discord.Member, *, role: discord.Role):
    if role in user.roles:
        await user.remove_roles(role, reason=f"Role removed by {ctx.author}")
        await ctx.send(embed=success_embed("➖  Role Removed", f"Removed {role.mention} from {user.mention}"))
    else:
        await user.add_roles(role, reason=f"Role added by {ctx.author}")
        await ctx.send(embed=success_embed("➕  Role Added", f"Added {role.mention} to {user.mention}"))
    await ctx.message.delete()

@tree.command(name="role", description="Add or remove a role from a user")
@app_commands.describe(user="User to modify", role="Role to add/remove")
@app_commands.default_permissions(manage_roles=True)
async def role_slash(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if role in user.roles:
        await user.remove_roles(role, reason=f"Role removed by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed("➖  Role Removed", f"Removed {role.mention} from {user.mention}"),
            ephemeral=True
        )
    else:
        await user.add_roles(role, reason=f"Role added by {interaction.user}")
        await interaction.response.send_message(
            embed=success_embed("➕  Role Added", f"Added {role.mention} to {user.mention}"),
            ephemeral=True
        )

# ── .note ─────────────────────────────────────────────────────────────────────
@bot.command(name="note")
@commands.has_permissions(manage_messages=True)
async def note_prefix(ctx, user: discord.Member, *, note_text: str):
    mod_notes.setdefault(user.id, []).append({
        "note": note_text,
        "by": str(ctx.author),
        "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    })
    await ctx.send(embed=success_embed("📝  Note Added", f"Added note to {user.mention}'s profile."))
    await ctx.message.delete()

@tree.command(name="note", description="Add a private moderator note about a user")
@app_commands.describe(user="User to add note to", note="The note text")
@app_commands.default_permissions(manage_messages=True)
async def note_slash(interaction: discord.Interaction, user: discord.Member, note: str):
    mod_notes.setdefault(user.id, []).append({
        "note": note,
        "by": str(interaction.user),
        "at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    })
    await interaction.response.send_message(
        embed=success_embed("📝  Note Added", f"Added note to {user.mention}'s profile."),
        ephemeral=True
    )

# ── .notes ────────────────────────────────────────────────────────────────────
@bot.command(name="notes")
@commands.has_permissions(manage_messages=True)
async def notes_prefix(ctx, user: discord.Member):
    user_notes = mod_notes.get(user.id, [])
    if not user_notes:
        await ctx.reply(f"📝 No notes for {user.mention}.", delete_after=10)
        return
    embed = discord.Embed(title=f"📝  Mod Notes for {user}", color=0x5865F2)
    for i, n in enumerate(user_notes, 1):
        embed.add_field(name=f"Note #{i}", value=f"{n['note']}\n_— {n['by']} ({n['at']})_", inline=False)
    await ctx.send(embed=embed)

@tree.command(name="notes", description="View all moderator notes for a user")
@app_commands.describe(user="User to view notes for")
@app_commands.default_permissions(manage_messages=True)
async def notes_slash(interaction: discord.Interaction, user: discord.Member):
    user_notes = mod_notes.get(user.id, [])
    if not user_notes:
        await interaction.response.send_message(f"📝 No notes for {user.mention}.", ephemeral=True)
        return
    embed = discord.Embed(title=f"📝  Mod Notes for {user}", color=0x5865F2)
    for i, n in enumerate(user_notes, 1):
        embed.add_field(name=f"Note #{i}", value=f"{n['note']}\n_— {n['by']} ({n['at']})_", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── .filter ───────────────────────────────────────────────────────────────────
@bot.command(name="filter")
@commands.has_permissions(manage_messages=True)
async def filter_prefix(ctx, action: str, *, word: str = None):
    if action.lower() == "add" and word:
        word_filter.add(word.lower())
        await ctx.send(embed=success_embed("🚫  Word Added to Filter", f"Messages containing `{word}` will be auto-deleted."))
    elif action.lower() == "remove" and word:
        word_filter.discard(word.lower())
        await ctx.send(embed=success_embed("✅  Word Removed from Filter", f"`{word}` is no longer filtered."))
    elif action.lower() == "list":
        if not word_filter:
            await ctx.reply("📝 No words in filter.", delete_after=10)
            return
        await ctx.send(embed=discord.Embed(
            title="🚫  Filtered Words",
            description="\n".join(f"• `{w}`" for w in word_filter),
            color=0xED4245
        ))
    else:
        await ctx.reply("Usage: `.filter add/remove/list [word]`", delete_after=10)
    await ctx.message.delete()

@tree.command(name="filter", description="Manage the word filter")
@app_commands.describe(action="add/remove/list", word="Word to add or remove (not needed for list)")
@app_commands.default_permissions(manage_messages=True)
async def filter_slash(interaction: discord.Interaction, action: str, word: str = None):
    if action.lower() == "add" and word:
        word_filter.add(word.lower())
        await interaction.response.send_message(
            embed=success_embed("🚫  Word Added to Filter", f"Messages containing `{word}` will be auto-deleted."),
            ephemeral=True
        )
    elif action.lower() == "remove" and word:
        word_filter.discard(word.lower())
        await interaction.response.send_message(
            embed=success_embed("✅  Word Removed from Filter", f"`{word}` is no longer filtered."),
            ephemeral=True
        )
    elif action.lower() == "list":
        if not word_filter:
            await interaction.response.send_message("📝 No words in filter.", ephemeral=True)
            return
        await interaction.response.send_message(embed=discord.Embed(
            title="🚫  Filtered Words",
            description="\n".join(f"• `{w}`" for w in word_filter),
            color=0xED4245
        ), ephemeral=True)
    else:
        await interaction.response.send_message("Specify action: add/remove/list", ephemeral=True)

# ── .antiraid ─────────────────────────────────────────────────────────────────
@bot.command(name="antiraid")
@commands.has_permissions(administrator=True)
async def antiraid_prefix(ctx, status: str):
    global antiraid_enabled
    if status.lower() == "on":
        antiraid_enabled = True
        await ctx.send(embed=success_embed("🛡️  Anti-Raid Enabled", "New accounts joining rapidly will be auto-kicked."))
    elif status.lower() == "off":
        antiraid_enabled = False
        await ctx.send(embed=success_embed("🛡️  Anti-Raid Disabled", "Anti-raid protection is now off."))
    else:
        await ctx.reply("Usage: `.antiraid on/off`", delete_after=10)
    await ctx.message.delete()

@tree.command(name="antiraid", description="Toggle anti-raid protection")
@app_commands.describe(enabled="Turn on or off")
@app_commands.default_permissions(administrator=True)
async def antiraid_slash(interaction: discord.Interaction, enabled: bool):
    global antiraid_enabled
    antiraid_enabled = enabled
    if enabled:
        await interaction.response.send_message(
            embed=success_embed("🛡️  Anti-Raid Enabled", "New accounts will be auto-kicked if joining rapidly."),
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=success_embed("🛡️  Anti-Raid Disabled", "Anti-raid protection is off."),
            ephemeral=True
        )

# ── .avatar ───────────────────────────────────────────────────────────────────
@bot.command(name="avatar")
async def avatar_prefix(ctx, user: discord.Member = None):
    user = user or ctx.author
    embed = discord.Embed(title=f"Avatar — {user}", color=0x5865F2)
    embed.set_image(url=user.display_avatar.url)
    await ctx.send(embed=embed)

@tree.command(name="avatar", description="Show a user's avatar")
@app_commands.describe(user="User to show avatar for (default: you)")
async def avatar_slash(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"Avatar — {user}", color=0x5865F2)
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── .serverinfo ───────────────────────────────────────────────────────────────
@bot.command(name="serverinfo")
async def serverinfo_prefix(ctx):
    g = ctx.guild
    embed = discord.Embed(title=f"📊  {g.name}", color=0x5865F2)
    embed.set_thumbnail(url=g.icon.url if g.icon else None)
    embed.add_field(name="Owner", value=g.owner.mention, inline=True)
    embed.add_field(name="Members", value=g.member_count, inline=True)
    embed.add_field(name="Roles", value=len(g.roles), inline=True)
    embed.add_field(name="Created", value=g.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field(name="Channels", value=f"Text: {len(g.text_channels)} • Voice: {len(g.voice_channels)}", inline=False)
    await ctx.send(embed=embed)

@tree.command(name="serverinfo", description="Show server information")
async def serverinfo_slash(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"📊  {g.name}", color=0x5865F2)
    embed.set_thumbnail(url=g.icon.url if g.icon else None)
    embed.add_field(name="Owner", value=g.owner.mention, inline=True)
    embed.add_field(name="Members", value=g.member_count, inline=True)
    embed.add_field(name="Roles", value=len(g.roles), inline=True)
    embed.add_field(name="Created", value=g.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field(name="Channels", value=f"Text: {len(g.text_channels)} • Voice: {len(g.voice_channels)}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── Auto-moderation listeners ─────────────────────────────────────────────────
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # Word filter
    if word_filter and any(word in message.content.lower() for word in word_filter):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} your message contained a filtered word.",
                delete_after=5
            )
        except:
            pass
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    # Anti-raid: kick accounts < 7 days old
    if antiraid_enabled:
        account_age = (datetime.now(timezone.utc) - member.created_at).days
        if account_age < 7:
            try:
                await member.kick(reason="Anti-raid: Account too new")
            except:
                pass


# ── .reviewpanel / /reviewpanel ───────────────────────────────────────────────
@bot.command(name="reviewpanel")
@commands.has_permissions(administrator=True)
async def reviewpanel_prefix(ctx, channel: discord.TextChannel):
    global REVIEW_CHANNEL_ID
    REVIEW_CHANNEL_ID = channel.id
    await ctx.send(embed=success_embed(
        "✅  Review Channel Updated",
        f"Chat ban review panels will now be sent to {channel.mention}."
    ))
    await ctx.message.delete()

@tree.command(name="reviewpanel", description="Set the channel where chatban review panels are sent")
@app_commands.describe(channel="Channel for review panels")
@app_commands.default_permissions(administrator=True)
async def reviewpanel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    global REVIEW_CHANNEL_ID
    REVIEW_CHANNEL_ID = channel.id
    await interaction.response.send_message(
        embed=success_embed(
            "✅  Review Channel Updated",
            f"Chat ban review panels will now be sent to {channel.mention}."
        ),
        ephemeral=True
    )

# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_command_completion(ctx):
    """Auto-delete command messages after successful execution."""
    try:
        if ctx.command and not ctx.command.name in ['modhelp', 'serverinfo', 'avatar']:
            await ctx.message.delete()
    except Exception:
        pass


@bot.event  
async def on_mention(message):
    """Respond when bot is mentioned."""
    if message.author.bot or not bot.user.mentioned_in(message):
        return
    if message.reference:  # Reply to another message
        return
    embed = discord.Embed(
        title="👋  Hi there!",
        description=(
            f"I'm **{bot.user.name}**, your moderation assistant.\n\n"
            "Type `.modhelp` or `/modhelp` to see all commands!"
        ),
        color=0x5865F2
    )
    await message.reply(embed=embed, mention_author=False)


@bot.event
async def on_member_join(member):
    """Log new member joins."""
    channel = member.guild.system_channel
    if channel:
        account_age = (datetime.now(timezone.utc) - member.created_at).days
        warning = f"⚠️ Account is only **{account_age} days old**" if account_age < 7 else ""
        embed = discord.Embed(
            title="📥  Member Joined",
            description=f"{member.mention} joined the server.\n{warning}",
            color=0x57F287
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id} • Account created {member.created_at.strftime('%d %b %Y')}")
        await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    """Log member leaves."""
    channel = member.guild.system_channel
    if channel:
        embed = discord.Embed(
            title="📤  Member Left",
            description=f"**{member}** left the server.",
            color=0xED4245
        )
        embed.set_footer(text=f"ID: {member.id}")
        await channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅  Logged in as {bot.user} ({bot.user.id})")
    bot.add_view(ChatbanReviewView(0, 0, 0, "", 0))
    await tree.sync()
    print("✅  Slash commands synced")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="🛡️ /modhelp or .modhelp")
    )

if __name__ == "__main__":
    bot.run(TOKEN)
