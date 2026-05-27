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
    embed = discord.Embed(title="🔨  User Banned",
        description=f"**{user}** banned.\n**Reason:** {reason}\n**By:** {ctx.author.mention}", color=0xED4245)
    await ctx.send(embed=embed)
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
    embed = discord.Embed(title="⚠️  User Warned", color=0xFEE75C,
        description=f"**User:** {user.mention}\n**Reason:** {reason}\n**By:** {ctx.author.mention}\n**Total warnings:** {count}")
    await send_to_logs(ctx.guild, embed)
    await ctx.send(embed=embed)
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
        description="Use `.command` or `?command` or `/command`. You can **@mention** users or use their ID.")
    embed.add_field(name="📋  General", value=(
        "`.usercheck @user` — Full mod history\n"
        "`.reviewpanel #channel` — Set review channel\n"
        "`.note @user [text]` — Add private mod note\n"
        "`.notes @user` — View all notes"
    ), inline=False)
    embed.add_field(name="⚠️  Warnings & Bans", value=(
        "`.warn @user [reason]` — Warn a user\n"
        "`.warnings @user` — View warnings\n"
        "`.clearwarnings @user` — Clear warnings\n"
        "`.chatban @user [time] [reason]` — Remove chat perms\n"
        "`.unchatban @user` — Lift chat ban"
    ), inline=False)
    embed.add_field(name="🔨  Kicks & Bans", value=(
        "`.kick @user [reason]` — Kick user\n"
        "`.ban @user [reason]` — Ban user\n"
        "`.unban [id]` — Unban user"
    ), inline=False)
    embed.add_field(name="🔕  Mute & Timeout", value=(
        "`.mute @user [time] [reason]` — Timeout\n"
        "`.unmute @user` — Remove timeout"
    ), inline=False)
    embed.add_field(name="🔒  Channel Management", value=(
        "`.lock [#channel]` — Lock channel\n"
        "`.unlock [#channel]` — Unlock channel\n"
        "`.lockdown` — Lock all channels\n"
        "`.nuke [#channel]` — Clone & delete channel"
    ), inline=False)
    embed.add_field(name="✏️  User Management", value=(
        "`.nickname @user [name]` — Change nickname\n"
        "`.role @user [@role]` — Add/remove role\n"
        "`.avatar [@user]` — Show avatar"
    ), inline=False)
    embed.add_field(name="🧹  Cleanup & Filter", value=(
        "`.purge [amount]` — Delete messages (max 100)\n"
        "`.slowmode [seconds]` — Set slowmode\n"
        "`.filter add/remove/list [word]` — Manage word filter"
    ), inline=False)
    embed.add_field(name="ℹ️  Server Info", value=(
        "`.serverinfo` — Server statistics\n"
        "`.avatar [@user]` — View user avatar"
    ), inline=False)
    embed.add_field(name="📊  Auto Features", value=(
        "**Auto-spam:** 6 messages in 10s → 5min mute\n"
        "**Auto-escalation:** 3 warns→1d ban, 5 warns→1w ban, 6 warns→1mo ban\n"
        "**Join/Leave logs:** New members logged with account age"
    ), inline=False)
    embed.set_footer(text="Duration: 30s / 10m / 2h / 1d  •  Prefix: . or ?  •  Watching over Sparky AI")
    await ctx.send(embed=embed)

# ════════════════════════════════════════════════════════════════════════════════
# SLASH COMMANDS
# ════════════════════════════════════════════════════════════════════════════════



# ── .check ────────────────────────────────────────────────────────────────────
# In-memory logs for kicks and bans
kick_log: dict[int, list[dict]] = {}
ban_log: dict[int, list[dict]] = {}
chatban_log: dict[int, list[dict]] = {}

@bot.command(name="usercheck")
@commands.has_permissions(manage_messages=True)
async def usercheck_prefix(ctx, user: discord.Member):
    await _send_check(ctx.channel, user, ctx.guild)

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

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await channel.set_permissions(ctx.guild.default_role, send_messages=None,
                                   reason=f"Channel unlocked by {ctx.author}")
    await ctx.send(embed=success_embed("🔓  Channel Unlocked", f"{channel.mention} has been unlocked."))
    await ctx.message.delete()

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

@bot.command(name="nuke")
@commands.has_permissions(manage_channels=True)
async def nuke_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    position = channel.position
    new_channel = await channel.clone(reason=f"Channel nuked by {ctx.author}")
    await new_channel.edit(position=position)
    await channel.delete(reason=f"Channel nuked by {ctx.author}")
    embed = success_embed("💥  Channel Nuked", f"This channel was nuked by {ctx.author.mention}.")
    embed.set_image(url="https://media.giphy.com/media/MDJ9IbxxvDUQM/giphy.gif")
    await new_channel.send(embed=embed)

@bot.command(name="nickname")
@commands.has_permissions(manage_nicknames=True)
async def nickname_prefix(ctx, user: discord.Member, *, nickname: str = None):
    old_nick = user.display_name
    await user.edit(nick=nickname, reason=f"Nickname changed by {ctx.author}")
    new_text = f"`{nickname}`" if nickname else "removed"
    await ctx.send(embed=success_embed("✏️  Nickname Changed", 
        f"{user.mention}'s nickname changed from `{old_nick}` to {new_text}."))
    await ctx.message.delete()

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

@bot.event
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


# ── .logschannel / /logschannel ───────────────────────────────────────────────
@bot.command(name="logschannel")
@commands.has_permissions(administrator=True)
async def logschannel_prefix(ctx, channel: discord.TextChannel):
    logs_channels[ctx.guild.id] = channel.id
    await ctx.send(embed=success_embed("📋  Logs Channel Set", f"Logs will now be sent to {channel.mention}."))
    await ctx.message.delete()

@tree.command(name="logschannel", description="Set the channel for moderation logs and audit activity")
@app_commands.describe(channel="Channel to send logs to")
@app_commands.default_permissions(administrator=True)
async def logschannel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    logs_channels[interaction.guild.id] = channel.id
    await interaction.response.send_message(
        embed=success_embed("📋  Logs Channel Set", f"Logs will now be sent to {channel.mention}."),
        ephemeral=True
    )

async def send_to_logs(guild: discord.Guild, embed: discord.Embed):
    """Send an embed to the configured logs channel and ghost ping the owner."""
    channel_id = logs_channels.get(guild.id)
    if not channel_id:
        return
    
    channel = guild.get_channel(channel_id)
    if not channel:
        return
    
    try:
        # Send log with ghost ping (mention that disappears after sending)
        msg = await channel.send(f"<@{guild.owner_id}>", embed=embed, allowed_mentions=discord.AllowedMentions(users=False))
        # The ping will show in audit log but won't actually notify the owner
    except discord.Forbidden:
        pass


# ── .logschannel ──────────────────────────────────────────────────────────────
@bot.command(name="logschannel")
@commands.has_permissions(administrator=True)
async def logschannel_prefix(ctx, channel: discord.TextChannel):
    logs_channels[ctx.guild.id] = channel.id
    await ctx.send(embed=success_embed("📋  Logs Channel Set", f"Logs will now be sent to {channel.mention}."))
    await ctx.message.delete()

@tree.command(name="logschannel", description="Set channel for moderation logs")
@app_commands.describe(channel="Channel for logs")
@app_commands.default_permissions(administrator=True)
async def logschannel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    logs_channels[interaction.guild.id] = channel.id
    await interaction.response.send_message(
        embed=success_embed("📋  Logs Channel Set", f"Logs will now be sent to {channel.mention}."),
        ephemeral=True
    )


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
        activity=discord.Activity(type=discord.ActivityType.watching, name="Watching over Sparky AI")
    )

if __name__ == "__main__":
    bot.run(TOKEN)
