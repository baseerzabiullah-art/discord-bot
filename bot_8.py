import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import re
import time
import asyncio
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# ── Environment ─────────────────────────────────────────────────
TOKEN    = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
OWNER_ID = os.getenv("OWNER_ID")

if not TOKEN:
    raise RuntimeError("[ERROR] DISCORD_TOKEN is not set. Please check your .env file.")

# ── Intents ──────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members         = True
intents.message_content = True
intents.moderation      = True

# ── Bot ──────────────────────────────────────────────────────────
PREFIXES = ['.', '?']

def get_prefix(bot, message):
    for p in PREFIXES:
        if message.content.startswith(p):
            return p
    return '.'

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

# ── Spam tracking ────────────────────────────────────────────────
spam_map: dict[int, list[float]] = defaultdict(list)

# ════════════════════════════════════════════════════════════════
#  DATABASE (JSON)
# ════════════════════════════════════════════════════════════════
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def _load(filename: str) -> dict:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(filename: str, data: dict):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# Warnings
def db_get_warnings(guild_id, user_id):
    d = _load("warnings.json")
    return d.get(str(guild_id), {}).get(str(user_id), [])

def db_add_warning(guild_id, user_id, moderator_id, reason):
    d = _load("warnings.json")
    gid, uid = str(guild_id), str(user_id)
    d.setdefault(gid, {}).setdefault(uid, [])
    entry = {"id": int(time.time() * 1000), "moderatorId": str(moderator_id),
             "reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()}
    d[gid][uid].append(entry)
    _save("warnings.json", d)
    return d[gid][uid]

def db_remove_warning(guild_id, user_id, warning_id):
    d = _load("warnings.json")
    gid, uid = str(guild_id), str(user_id)
    if gid not in d or uid not in d[gid]:
        return False
    before = len(d[gid][uid])
    d[gid][uid] = [w for w in d[gid][uid] if w["id"] != warning_id]
    _save("warnings.json", d)
    return len(d[gid][uid]) < before

# Mod actions
def db_add_mod_action(guild_id, user_id, action: dict):
    d = _load("modactions.json")
    gid, uid = str(guild_id), str(user_id)
    d.setdefault(gid, {}).setdefault(uid, [])
    action["timestamp"] = datetime.now(timezone.utc).isoformat()
    d[gid][uid].append(action)
    _save("modactions.json", d)

def db_get_mod_actions(guild_id, user_id):
    d = _load("modactions.json")
    return d.get(str(guild_id), {}).get(str(user_id), [])

# Notes
def db_add_note(guild_id, user_id, moderator_id, note):
    d = _load("notes.json")
    gid, uid = str(guild_id), str(user_id)
    d.setdefault(gid, {}).setdefault(uid, [])
    entry = {"id": int(time.time() * 1000), "moderatorId": str(moderator_id),
             "note": note, "timestamp": datetime.now(timezone.utc).isoformat()}
    d[gid][uid].append(entry)
    _save("notes.json", d)
    return entry

def db_get_notes(guild_id, user_id):
    d = _load("notes.json")
    return d.get(str(guild_id), {}).get(str(user_id), [])

def db_remove_note(guild_id, user_id, note_id):
    d = _load("notes.json")
    gid, uid = str(guild_id), str(user_id)
    if gid not in d or uid not in d[gid]:
        return False
    before = len(d[gid][uid])
    d[gid][uid] = [n for n in d[gid][uid] if n["id"] != note_id]
    _save("notes.json", d)
    return len(d[gid][uid]) < before

# Config
def db_get_config(guild_id):
    d = _load("config.json")
    return d.get(str(guild_id), {})

def db_set_config(guild_id, key, value):
    d = _load("config.json")
    gid = str(guild_id)
    d.setdefault(gid, {})[key] = value
    _save("config.json", d)

# Filter words
def db_get_filter_words(guild_id):
    d = _load("filter.json")
    return d.get(str(guild_id), [])

def db_add_filter_word(guild_id, word):
    d = _load("filter.json")
    gid = str(guild_id)
    d.setdefault(gid, [])
    if word.lower() not in d[gid]:
        d[gid].append(word.lower())
        _save("filter.json", d)
        return True
    return False

def db_remove_filter_word(guild_id, word):
    d = _load("filter.json")
    gid = str(guild_id)
    if gid not in d:
        return False
    before = len(d[gid])
    d[gid] = [w for w in d[gid] if w != word.lower()]
    _save("filter.json", d)
    return len(d[gid]) < before

# Chatbans
def db_set_chatban(guild_id, user_id, data):
    d = _load("chatbans.json")
    gid, uid = str(guild_id), str(user_id)
    d.setdefault(gid, {})[uid] = data
    _save("chatbans.json", d)

def db_get_chatban(guild_id, user_id):
    d = _load("chatbans.json")
    return d.get(str(guild_id), {}).get(str(user_id), None)

def db_remove_chatban(guild_id, user_id):
    d = _load("chatbans.json")
    gid, uid = str(guild_id), str(user_id)
    if gid in d and uid in d[gid]:
        del d[gid][uid]
        _save("chatbans.json", d)

# ════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════
COLORS = {
    "success": 0x57F287,
    "error":   0xED4245,
    "warn":    0xFEE75C,
    "info":    0x5865F2,
    "mod":     0xEB459E,
    "log":     0x23272A,
}

def success_embed(title, description):
    return discord.Embed(title=f"✅ {title}", description=description,
                         color=COLORS["success"], timestamp=datetime.now(timezone.utc))

def error_embed(title, description):
    return discord.Embed(title=f"❌ {title}", description=description,
                         color=COLORS["error"], timestamp=datetime.now(timezone.utc))

def warn_embed(title, description):
    return discord.Embed(title=f"⚠️ {title}", description=description,
                         color=COLORS["warn"], timestamp=datetime.now(timezone.utc))

def info_embed(title, description):
    return discord.Embed(title=f"ℹ️ {title}", description=description,
                         color=COLORS["info"], timestamp=datetime.now(timezone.utc))

def mod_embed(action, moderator, target, reason, extra: dict = {}):
    target_str = f"{getattr(target, 'name', str(target))} (`{getattr(target, 'id', target)}`)"
    mod_str    = getattr(moderator, 'name', str(moderator))
    embed = discord.Embed(title=f"🔨 {action}", color=COLORS["mod"],
                          timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Target",    value=target_str,             inline=True)
    embed.add_field(name="Moderator", value=mod_str,                inline=True)
    embed.add_field(name="Reason",    value=reason or "No reason provided", inline=False)
    for k, v in extra.items():
        embed.add_field(name=k, value=str(v), inline=True)
    return embed

def has_mod_permission(member: discord.Member) -> bool:
    p = member.guild_permissions
    return any([p.moderate_members, p.ban_members, p.kick_members, p.administrator])

def has_admin_permission(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild

def account_age_days(user: discord.User) -> int:
    return (datetime.now(timezone.utc) - user.created_at).days

async def send_log(guild: discord.Guild, embed: discord.Embed):
    cfg = db_get_config(guild.id)
    channel_id = cfg.get("logsChannelId")
    if not channel_id:
        return
    ch = guild.get_channel(int(channel_id))
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

def parse_duration(s: str):
    match = re.match(r'^(\d+)(s|m|h|d|w)$', s)
    if not match:
        return None
    num, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    seconds = num * multipliers[unit]
    if seconds > 28 * 86400:
        return None
    return timedelta(seconds=seconds)

async def resolve_user(guild: discord.Guild, raw: str):
    if not raw:
        return None, None
    cleaned = re.sub(r'[<@!>]', '', raw).strip()
    try:
        member = guild.get_member(int(cleaned)) or await guild.fetch_member(int(cleaned))
        if member:
            return member.user if hasattr(member, 'user') else member._user, member
    except Exception:
        pass
    try:
        user = await bot.fetch_user(int(cleaned))
        if user:
            return user, None
    except Exception:
        pass
    return None, None

# ════════════════════════════════════════════════════════════════
#  CHATBAN LOGIC
# ════════════════════════════════════════════════════════════════
async def apply_chatban(guild: discord.Guild, user_id: int, reason: str,
                        moderator_id: int, duration_seconds: int = None):
    try:
        await guild.fetch_member(user_id)
    except Exception:
        return False

    for channel in guild.channels:
        if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            continue
        try:
            await channel.set_permissions(
                discord.Object(id=user_id),
                send_messages=False,
                add_reactions=False,
                create_public_threads=False,
                create_private_threads=False,
                send_messages_in_threads=False
            )
        except Exception:
            pass

    expires_at = None
    if duration_seconds:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).isoformat()

    db_set_chatban(guild.id, user_id, {
        "moderatorId": str(moderator_id),
        "reason": reason,
        "appliedAt": datetime.now(timezone.utc).isoformat(),
        "expiresAt": expires_at
    })
    return True

async def remove_chatban(guild: discord.Guild, user_id: int):
    for channel in guild.channels:
        if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            continue
        try:
            overwrite = channel.overwrites_for(discord.Object(id=user_id))
            if overwrite.is_empty():
                continue
            await channel.set_permissions(discord.Object(id=user_id), overwrite=None)
        except Exception:
            pass
    db_remove_chatban(guild.id, user_id)
    return True

# ════════════════════════════════════════════════════════════════
#  EVENTS
# ════════════════════════════════════════════════════════════════
@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="over Sparky AI"),
        status=discord.Status.online
    )
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"[DEPLOY] Slash commands synced to guild {GUILD_ID}")
    else:
        await bot.tree.sync()
        print("[DEPLOY] Slash commands synced globally")
    print(f"[READY] Logged in as {bot.user} — Bot is fully operational.")


@bot.event
async def on_member_join(member: discord.Member):
    cfg = db_get_config(member.guild.id)
    if not cfg.get("logsChannelId"):
        return
    ch = member.guild.get_channel(int(cfg["logsChannelId"]))
    if not ch:
        return
    age = account_age_days(member)
    color = 0xFEE75C if age < 7 else 0x57F287
    title = f"📥 Member Joined{'  ⚠️ NEW ACCOUNT' if age < 7 else ''}"
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User",          value=f"{member} (`{member.id}`)",                                  inline=True)
    embed.add_field(name="Account Age",   value=f"{age} days",                                                inline=True)
    embed.add_field(name="Created",       value=f"<t:{int(member.created_at.timestamp())}:R>",                inline=True)
    embed.add_field(name="Total Members", value=str(member.guild.member_count),                               inline=True)
    if age < 7:
        embed.description = "⚠️ **This account is less than 7 days old!**"
    await ch.send(embed=embed)


@bot.event
async def on_member_remove(member: discord.Member):
    cfg = db_get_config(member.guild.id)
    if not cfg.get("logsChannelId"):
        return
    ch = member.guild.get_channel(int(cfg["logsChannelId"]))
    if not ch:
        return
    embed = discord.Embed(title="📤 Member Left", color=0xED4245,
                          timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User",          value=f"{member} (`{member.id}`)", inline=True)
    joined = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown"
    embed.add_field(name="Joined",        value=joined,                      inline=True)
    embed.add_field(name="Total Members", value=str(member.guild.member_count), inline=True)
    await ch.send(embed=embed)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # Word filter
    filter_words = db_get_filter_words(message.guild.id)
    if filter_words:
        lower = message.content.lower()
        if any(w in lower for w in filter_words):
            try:
                await message.delete()
            except Exception:
                pass
            warn = await message.channel.send(embed=warn_embed(
                "Message Filtered",
                f"{message.author.mention}, your message was removed for containing a banned word."
            ))
            await asyncio.sleep(5)
            try:
                await warn.delete()
            except Exception:
                pass
            return

    # Anti-spam: 6+ messages in 10 seconds → 5min timeout
    now = time.time()
    uid = message.author.id
    spam_map[uid] = [t for t in spam_map[uid] if now - t < 10]
    spam_map[uid].append(now)

    if len(spam_map[uid]) >= 6:
        spam_map[uid] = []
        member = message.guild.get_member(uid)
        if member and not member.guild_permissions.manage_messages:
            try:
                await member.timeout(timedelta(minutes=5), reason="Auto: spam detection (6+ messages in 10s)")
                embed = mod_embed("Auto Mute (Spam)", bot.user, message.author,
                                  "Spam detection triggered", {"Duration": "5 minutes"})
                embed.color = COLORS["warn"]
                await send_log(message.guild, embed)
                warn = await message.channel.send(embed=warn_embed(
                    "Spam Detected",
                    f"{message.author.mention} has been muted for 5 minutes for spamming."
                ))
                await asyncio.sleep(6)
                try:
                    await warn.delete()
                except Exception:
                    pass
            except Exception:
                pass
        return

    await bot.process_commands(message)

# ════════════════════════════════════════════════════════════════
#  SHARED COMMAND LOGIC (used by both prefix and slash)
# ════════════════════════════════════════════════════════════════

async def do_warn(guild, moderator, target_raw, reason, reply):
    user, member = await resolve_user(guild, str(target_raw))
    if not user:
        return await reply(embed=error_embed("User Not Found", "Could not find that user."))

    warnings = db_add_warning(guild.id, user.id, moderator.id, reason or "No reason provided")
    count = len(warnings)
    db_add_mod_action(guild.id, user.id, {"type": "WARN", "moderatorId": str(moderator.id), "reason": reason})

    escalation = ""
    if count == 3:
        await apply_chatban(guild, user.id, "Auto: 3 warnings", bot.user.id, 86400)
        escalation = "\n⚡ **Auto-escalation:** 1-day chatban applied."
    elif count == 5:
        await apply_chatban(guild, user.id, "Auto: 5 warnings", bot.user.id, 7 * 86400)
        escalation = "\n⚡ **Auto-escalation:** 1-week chatban applied."
        try:
            await user.send(embed=warn_embed("Final Warning",
                f"You have received 5 warnings in **{guild.name}**. Further violations will result in a temporary ban."))
        except Exception:
            pass
    elif count >= 6:
        try:
            await guild.ban(user, reason="Auto: 6 warnings - 1 month temp ban", delete_message_seconds=0)
            db_add_mod_action(guild.id, user.id, {
                "type": "TEMPBAN", "moderatorId": str(bot.user.id),
                "reason": "Auto: 6 warnings",
                "expiresAt": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            })
        except Exception:
            pass
        escalation = "\n⚡ **Auto-escalation:** 1-month temporary ban applied."

    embed = mod_embed("Warning Issued", moderator, user, reason or "No reason provided", {"Warning Count": str(count)})
    if escalation:
        embed.description = (embed.description or "") + escalation
    await send_log(guild, embed)
    await reply(embed=embed)
    try:
        await user.send(embed=warn_embed("You were warned",
            f"**Server:** {guild.name}\n**Reason:** {reason}\n**Total Warnings:** {count}"))
    except Exception:
        pass


async def do_mute(guild, moderator, target_raw, duration_str, reason, reply):
    user, member = await resolve_user(guild, str(target_raw))
    if not member:
        return await reply(embed=error_embed("User Not Found", "Could not find that member."))
    td = parse_duration(duration_str)
    if not td:
        return await reply(embed=error_embed("Invalid Duration", "Use format: 10m, 1h, 2d (max 28d)"))
    try:
        await member.timeout(td, reason=reason or "No reason provided")
    except Exception as e:
        return await reply(embed=error_embed("Failed", str(e)))
    db_add_mod_action(guild.id, user.id, {"type": "MUTE", "moderatorId": str(moderator.id),
                                           "reason": reason, "duration": duration_str})
    embed = mod_embed("Member Muted", moderator, user, reason or "No reason provided", {"Duration": duration_str})
    await send_log(guild, embed)
    await reply(embed=embed)


async def do_kick(guild, moderator, target_raw, reason, reply):
    user, member = await resolve_user(guild, str(target_raw))
    if not member:
        return await reply(embed=error_embed("User Not Found", "Could not find that member."))
    try:
        await member.kick(reason=reason or "No reason provided")
    except Exception as e:
        return await reply(embed=error_embed("Failed", str(e)))
    db_add_mod_action(guild.id, user.id, {"type": "KICK", "moderatorId": str(moderator.id), "reason": reason})
    embed = mod_embed("Member Kicked", moderator, user, reason or "No reason provided")
    await send_log(guild, embed)
    await reply(embed=embed)


async def do_ban(guild, moderator, target_raw, reason, reply):
    user, _ = await resolve_user(guild, str(target_raw))
    if not user:
        return await reply(embed=error_embed("User Not Found", "Could not find that user."))
    try:
        await guild.ban(user, reason=reason or "No reason provided", delete_message_seconds=604800)
    except Exception as e:
        return await reply(embed=error_embed("Failed", str(e)))
    db_add_mod_action(guild.id, user.id, {"type": "BAN", "moderatorId": str(moderator.id), "reason": reason})
    embed = mod_embed("Member Banned", moderator, user, reason or "No reason provided")
    await send_log(guild, embed)
    cfg = db_get_config(guild.id)
    if cfg.get("logsChannelId") and OWNER_ID:
        ch = guild.get_channel(int(cfg["logsChannelId"]))
        if ch:
            try:
                ping = await ch.send(f"<@{OWNER_ID}>")
                await ping.delete()
            except Exception:
                pass
    await reply(embed=embed)

# ════════════════════════════════════════════════════════════════
#  PREFIX COMMANDS
# ════════════════════════════════════════════════════════════════

def mod_check():
    async def predicate(ctx):
        if not has_mod_permission(ctx.author):
            await ctx.reply(embed=error_embed("No Permission", "You need moderation permissions."))
            return False
        return True
    return commands.check(predicate)

def admin_check():
    async def predicate(ctx):
        if not has_admin_permission(ctx.author):
            await ctx.reply(embed=error_embed("No Permission", "You need Manage Guild permission."))
            return False
        return True
    return commands.check(predicate)

# ── WARN ────────────────────────────────────────────────────────
@bot.command(name="warn")
@mod_check()
async def prefix_warn(ctx, target=None, *, reason="No reason provided"):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    await do_warn(ctx.guild, ctx.author, target, reason, ctx.reply)

# ── WARNINGS ────────────────────────────────────────────────────
@bot.command(name="warnings", aliases=["infractions"])
@mod_check()
async def prefix_warnings(ctx, target=None):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    warns = db_get_warnings(ctx.guild.id, user.id)
    if not warns:
        return await ctx.reply(embed=info_embed("No Warnings", f"{user} has no warnings."))
    desc = "\n\n".join(
        f"**#{i+1}** • <t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:R>\n> {w['reason']}\n> *by <@{w['moderatorId']}>* • ID: `{w['id']}`"
        for i, w in enumerate(warns)
    )
    embed = discord.Embed(title=f"⚠️ Warnings for {user}", description=desc,
                          color=COLORS["warn"], timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"{len(warns)} total warning(s)")
    await ctx.reply(embed=embed)

# ── DELWARN ─────────────────────────────────────────────────────
@bot.command(name="delwarn", aliases=["removewarn"])
@mod_check()
async def prefix_delwarn(ctx, target=None, warn_id=None):
    if not target or not warn_id:
        return await ctx.reply(embed=error_embed("Usage", "`.delwarn <user> <id>`"))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    try:
        wid = int(warn_id)
    except ValueError:
        return await ctx.reply(embed=error_embed("Invalid ID", "Provide a valid warning ID."))
    removed = db_remove_warning(ctx.guild.id, user.id, wid)
    await ctx.reply(embed=success_embed("Warning Removed", f"Removed warning `{wid}` from {user}.") if removed
                    else error_embed("Not Found", "Warning ID not found."))

# ── CHATBAN ─────────────────────────────────────────────────────
@bot.command(name="chatban", aliases=["cb"])
@mod_check()
async def prefix_chatban(ctx, target=None, *, reason="No reason provided"):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    await apply_chatban(ctx.guild, user.id, reason, ctx.author.id)
    db_add_mod_action(ctx.guild.id, user.id, {"type": "CHATBAN", "moderatorId": str(ctx.author.id), "reason": reason})
    embed = mod_embed("Chatban Applied", ctx.author, user, reason)
    await send_log(ctx.guild, embed)
    await ctx.reply(embed=embed)
    try:
        await user.send(embed=error_embed("Chatbanned", f"You have been chatbanned in **{ctx.guild.name}**.\n**Reason:** {reason}"))
    except Exception:
        pass

# ── UNCHATBAN ───────────────────────────────────────────────────
@bot.command(name="unchatban", aliases=["uncb"])
@mod_check()
async def prefix_unchatban(ctx, target=None):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    await remove_chatban(ctx.guild, user.id)
    db_add_mod_action(ctx.guild.id, user.id, {"type": "UNCHATBAN", "moderatorId": str(ctx.author.id)})
    embed = mod_embed("Chatban Removed", ctx.author, user, "Chatban lifted")
    await send_log(ctx.guild, embed)
    await ctx.reply(embed=embed)

# ── MUTE ────────────────────────────────────────────────────────
@bot.command(name="mute", aliases=["timeout"])
@mod_check()
async def prefix_mute(ctx, target=None, duration_str="10m", *, reason="No reason provided"):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    await do_mute(ctx.guild, ctx.author, target, duration_str, reason, ctx.reply)

# ── UNMUTE ──────────────────────────────────────────────────────
@bot.command(name="unmute", aliases=["untimeout"])
@mod_check()
async def prefix_unmute(ctx, target=None):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    user, member = await resolve_user(ctx.guild, target)
    if not member:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that member."))
    try:
        await member.timeout(None, reason="Mute removed")
    except Exception as e:
        return await ctx.reply(embed=error_embed("Failed", str(e)))
    db_add_mod_action(ctx.guild.id, user.id, {"type": "UNMUTE", "moderatorId": str(ctx.author.id)})
    embed = mod_embed("Member Unmuted", ctx.author, user, "Mute removed")
    await send_log(ctx.guild, embed)
    await ctx.reply(embed=embed)

# ── KICK ────────────────────────────────────────────────────────
@bot.command(name="kick")
async def prefix_kick(ctx, target=None, *, reason="No reason provided"):
    if not ctx.author.guild_permissions.kick_members:
        return await ctx.reply(embed=error_embed("No Permission", "You need Kick Members permission."))
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    await do_kick(ctx.guild, ctx.author, target, reason, ctx.reply)

# ── BAN ─────────────────────────────────────────────────────────
@bot.command(name="ban")
async def prefix_ban(ctx, target=None, *, reason="No reason provided"):
    if not ctx.author.guild_permissions.ban_members:
        return await ctx.reply(embed=error_embed("No Permission", "You need Ban Members permission."))
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    await do_ban(ctx.guild, ctx.author, target, reason, ctx.reply)

# ── UNBAN ───────────────────────────────────────────────────────
@bot.command(name="unban")
async def prefix_unban(ctx, user_id=None, *, reason="No reason provided"):
    if not ctx.author.guild_permissions.ban_members:
        return await ctx.reply(embed=error_embed("No Permission", "You need Ban Members permission."))
    if not user_id:
        return await ctx.reply(embed=error_embed("Missing ID", "Provide a user ID."))
    cleaned = re.sub(r'[<@!>]', '', user_id).strip()
    try:
        ban_entry = await ctx.guild.fetch_ban(discord.Object(id=int(cleaned)))
    except discord.NotFound:
        return await ctx.reply(embed=error_embed("Not Banned", "That user is not banned."))
    await ctx.guild.unban(ban_entry.user, reason=reason)
    db_add_mod_action(ctx.guild.id, ban_entry.user.id, {"type": "UNBAN", "moderatorId": str(ctx.author.id), "reason": reason})
    embed = mod_embed("Member Unbanned", ctx.author, ban_entry.user, reason)
    await send_log(ctx.guild, embed)
    await ctx.reply(embed=embed)

# ── USERCHECK ───────────────────────────────────────────────────
@bot.command(name="usercheck", aliases=["uc", "check", "info"])
@mod_check()
async def prefix_usercheck(ctx, target=None):
    raw = target or str(ctx.author.id)
    user, member = await resolve_user(ctx.guild, raw)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    warns   = db_get_warnings(ctx.guild.id, user.id)
    actions = db_get_mod_actions(ctx.guild.id, user.id)
    age     = account_age_days(user)
    embed = discord.Embed(title=f"🔍 User Check: {user}", color=COLORS["info"],
                          timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User",            value=f"{user.mention} (`{user.id}`)",                      inline=True)
    embed.add_field(name="📅 Account Created", value=f"<t:{int(user.created_at.timestamp())}:R>",          inline=True)
    embed.add_field(name="📆 Account Age",     value=f"{age} days {'⚠️ NEW' if age < 7 else ''}",         inline=True)
    if member:
        embed.add_field(name="📥 Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:R>",       inline=True)
        roles = [r.mention for r in member.roles if r.id != ctx.guild.id]
        embed.add_field(name="🏷️ Roles", value=", ".join(roles) or "None", inline=False)
    warn_val = "\n".join(
        f"• {w['reason']} — <t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:R>"
        for w in warns[-3:]
    ) if warns else "None"
    embed.add_field(name=f"⚠️ Warnings ({len(warns)})", value=warn_val, inline=False)
    action_val = "\n".join(
        f"• **{a['type']}** — {a.get('reason','')} <t:{int(datetime.fromisoformat(a['timestamp']).timestamp())}:R>"
        for a in actions[-5:]
    ) if actions else "None"
    embed.add_field(name=f"🔨 Recent Actions ({len(actions)})", value=action_val, inline=False)
    alts = [m for m in ctx.guild.members
            if m.id != user.id and abs((m.created_at - user.created_at).total_seconds()) < 86400]
    if alts:
        embed.add_field(name="🔁 Possible Alts", value="\n".join(str(m) for m in alts[:10]), inline=False)
    await ctx.reply(embed=embed)

# ── NOTE / NOTES / DELNOTE ──────────────────────────────────────
@bot.command(name="note")
@mod_check()
async def prefix_note(ctx, target=None, *, text=None):
    if not target or not text:
        return await ctx.reply(embed=error_embed("Usage", "`.note <user> <text>`"))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    entry = db_add_note(ctx.guild.id, user.id, ctx.author.id, text)
    await ctx.reply(embed=success_embed("Note Added", f"Note added for {user}.\n> {text}\nID: `{entry['id']}`"))

@bot.command(name="notes")
@mod_check()
async def prefix_notes(ctx, target=None):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    notes = db_get_notes(ctx.guild.id, user.id)
    if not notes:
        return await ctx.reply(embed=info_embed("No Notes", f"No notes for {user}."))
    desc = "\n\n".join(
        f"**#{i+1}** by <@{n['moderatorId']}> • <t:{int(datetime.fromisoformat(n['timestamp']).timestamp())}:R>\n> {n['note']}\n> ID: `{n['id']}`"
        for i, n in enumerate(notes)
    )
    embed = discord.Embed(title=f"📝 Notes for {user}", description=desc,
                          color=COLORS["info"], timestamp=datetime.now(timezone.utc))
    await ctx.reply(embed=embed)

@bot.command(name="delnote")
@mod_check()
async def prefix_delnote(ctx, target=None, note_id=None):
    if not target or not note_id:
        return await ctx.reply(embed=error_embed("Usage", "`.delnote <user> <id>`"))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    try:
        nid = int(note_id)
    except ValueError:
        return await ctx.reply(embed=error_embed("Invalid ID", "Provide a valid note ID."))
    removed = db_remove_note(ctx.guild.id, user.id, nid)
    await ctx.reply(embed=success_embed("Note Deleted", "Note removed.") if removed
                    else error_embed("Not Found", "Note ID not found."))

# ── LOCK / UNLOCK ───────────────────────────────────────────────
@bot.command(name="lock")
@admin_check()
async def prefix_lock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.reply(embed=success_embed("Channel Locked", f"{ctx.channel.mention} is now locked."))
        await send_log(ctx.guild, mod_embed("Channel Locked", ctx.author,
                       type("obj", (object,), {"name": ctx.channel.name, "id": ctx.channel.id})(),
                       "Manual lock"))
    except Exception as e:
        await ctx.reply(embed=error_embed("Failed", str(e)))

@bot.command(name="unlock")
@admin_check()
async def prefix_unlock(ctx):
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.reply(embed=success_embed("Channel Unlocked", f"{ctx.channel.mention} is now unlocked."))
    except Exception as e:
        await ctx.reply(embed=error_embed("Failed", str(e)))

# ── LOCKDOWN / UNLOCKALL ─────────────────────────────────────────
@bot.command(name="lockdown")
@admin_check()
async def prefix_lockdown(ctx):
    count = 0
    for ch in ctx.guild.text_channels:
        try:
            await ch.set_permissions(ctx.guild.default_role, send_messages=False)
            count += 1
        except Exception:
            pass
    await send_log(ctx.guild, mod_embed("🔒 SERVER LOCKDOWN", ctx.author,
                   type("obj", (object,), {"name": ctx.guild.name, "id": ctx.guild.id})(),
                   f"Locked {count} channels"))
    await ctx.reply(embed=warn_embed("Lockdown Active", f"Locked **{count}** channels."))

@bot.command(name="unlockall")
@admin_check()
async def prefix_unlockall(ctx):
    count = 0
    for ch in ctx.guild.text_channels:
        try:
            await ch.set_permissions(ctx.guild.default_role, send_messages=None)
            count += 1
        except Exception:
            pass
    await ctx.reply(embed=success_embed("Lockdown Lifted", f"Unlocked **{count}** channels."))

# ── NUKE ─────────────────────────────────────────────────────────
@bot.command(name="nuke")
@admin_check()
async def prefix_nuke(ctx):
    channel = ctx.channel
    try:
        new_ch = await channel.clone(name=channel.name, reason="Nuke command")
        await new_ch.edit(position=channel.position)
        await channel.delete(reason="Nuked")
        await new_ch.send(embed=success_embed("Channel Nuked", "💣 Channel has been nuked and recreated."))
        await send_log(ctx.guild, mod_embed("Channel Nuked", ctx.author,
                       type("obj", (object,), {"name": channel.name, "id": channel.id})(),
                       "Nuke command"))
    except Exception as e:
        await ctx.reply(embed=error_embed("Failed", str(e)))

# ── NICKNAME ─────────────────────────────────────────────────────
@bot.command(name="nickname", aliases=["nick"])
@mod_check()
async def prefix_nickname(ctx, target=None, *, new_nick=None):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    user, member = await resolve_user(ctx.guild, target)
    if not member:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that member."))
    try:
        await member.edit(nick=new_nick, reason=f"Changed by {ctx.author}")
        await ctx.reply(embed=success_embed("Nickname Changed",
            f"{user.mention}'s nickname set to: **{new_nick or '(reset)'}**"))
    except Exception as e:
        await ctx.reply(embed=error_embed("Failed", str(e)))

# ── ROLE ─────────────────────────────────────────────────────────
@bot.command(name="role")
@admin_check()
async def prefix_role(ctx, target=None, role_input=None):
    if not target or not role_input:
        return await ctx.reply(embed=error_embed("Usage", "`.role <user> <role>`"))
    user, member = await resolve_user(ctx.guild, target)
    if not member:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that member."))
    role_id = re.sub(r'[<@&>]', '', role_input).strip()
    role = ctx.guild.get_role(int(role_id)) if role_id.isdigit() else discord.utils.get(ctx.guild.roles, name=role_input)
    if not role:
        return await ctx.reply(embed=error_embed("Role Not Found", "Could not find that role."))
    try:
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.reply(embed=success_embed("Role Removed", f"Removed {role.mention} from {user}."))
        else:
            await member.add_roles(role)
            await ctx.reply(embed=success_embed("Role Added", f"Added {role.mention} to {user}."))
    except Exception as e:
        await ctx.reply(embed=error_embed("Failed", str(e)))

# ── PURGE ─────────────────────────────────────────────────────────
@bot.command(name="purge", aliases=["clear", "prune"])
async def prefix_purge(ctx, amount=None):
    if not ctx.author.guild_permissions.manage_messages:
        return await ctx.reply(embed=error_embed("No Permission", "You need Manage Messages permission."))
    try:
        n = int(amount)
        assert 1 <= n <= 100
    except Exception:
        return await ctx.reply(embed=error_embed("Invalid Amount", "Provide a number between 1 and 100."))
    try:
        deleted = await ctx.channel.purge(limit=n)
        msg = await ctx.channel.send(embed=success_embed("Purge Complete", f"Deleted **{len(deleted)}** messages."))
        await asyncio.sleep(4)
        await msg.delete()
    except Exception as e:
        await ctx.reply(embed=error_embed("Failed", str(e)))

# ── SLOWMODE ──────────────────────────────────────────────────────
@bot.command(name="slowmode", aliases=["slow"])
@mod_check()
async def prefix_slowmode(ctx, seconds=None):
    try:
        s = int(seconds)
        assert 0 <= s <= 21600
    except Exception:
        return await ctx.reply(embed=error_embed("Invalid", "Slowmode must be 0–21600 seconds."))
    try:
        await ctx.channel.edit(slowmode_delay=s)
        await ctx.reply(embed=success_embed("Slowmode Set",
            "Slowmode disabled." if s == 0 else f"Slowmode set to **{s}s**."))
    except Exception as e:
        await ctx.reply(embed=error_embed("Failed", str(e)))

# ── FILTER ────────────────────────────────────────────────────────
@bot.command(name="filter")
@mod_check()
async def prefix_filter(ctx, sub=None, word=None):
    if sub == "add":
        if not word:
            return await ctx.reply(embed=error_embed("Missing Word", "Provide a word to filter."))
        added = db_add_filter_word(ctx.guild.id, word)
        await ctx.reply(embed=success_embed("Word Added", f"`{word}` added to filter.") if added
                        else info_embed("Already Filtered", f"`{word}` is already in the filter."))
    elif sub in ("remove", "del"):
        if not word:
            return await ctx.reply(embed=error_embed("Missing Word", "Provide a word to remove."))
        removed = db_remove_filter_word(ctx.guild.id, word)
        await ctx.reply(embed=success_embed("Word Removed", f"`{word}` removed.") if removed
                        else error_embed("Not Found", f"`{word}` not in filter."))
    else:
        words = db_get_filter_words(ctx.guild.id)
        await ctx.reply(embed=info_embed("Filter List",
            ", ".join(f"`{w}`" for w in words) if words else "No filtered words."))

# ── AVATAR ───────────────────────────────────────────────────────
@bot.command(name="avatar", aliases=["av", "pfp"])
async def prefix_avatar(ctx, target=None):
    user, _ = await resolve_user(ctx.guild, target or str(ctx.author.id))
    user = user or ctx.author
    embed = discord.Embed(title=f"🖼️ {user}'s Avatar", color=COLORS["info"],
                          timestamp=datetime.now(timezone.utc))
    embed.set_image(url=user.display_avatar.url)
    png  = user.display_avatar.replace(format="png",  size=1024).url
    webp = user.display_avatar.replace(format="webp", size=1024).url
    jpg  = user.display_avatar.replace(format="jpg",  size=1024).url
    embed.description = f"[PNG]({png}) | [WebP]({webp}) | [JPG]({jpg})"
    await ctx.reply(embed=embed)

# ── LOGSCHANNEL ──────────────────────────────────────────────────
@bot.command(name="logschannel", aliases=["setlogs", "logs"])
@admin_check()
async def prefix_logschannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.reply(embed=error_embed("Missing Channel", "Mention or provide a channel ID."))
    db_set_config(ctx.guild.id, "logsChannelId", str(channel.id))
    await ctx.reply(embed=success_embed("Logs Channel Set", f"All mod logs will be sent to {channel.mention}."))

# ── SERVERINFO ───────────────────────────────────────────────────
@bot.command(name="serverinfo", aliases=["si", "server"])
async def prefix_serverinfo(ctx):
    g = ctx.guild
    embed = discord.Embed(title=f"📊 {g.name}", color=COLORS["info"],
                          timestamp=datetime.now(timezone.utc))
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="👑 Owner",        value=f"<@{g.owner_id}>",                        inline=True)
    embed.add_field(name="📅 Created",      value=f"<t:{int(g.created_at.timestamp())}:R>",  inline=True)
    embed.add_field(name="👥 Members",      value=str(g.member_count),                       inline=True)
    embed.add_field(name="💬 Channels",     value=str(len(g.channels)),                      inline=True)
    embed.add_field(name="🎭 Roles",        value=str(len(g.roles)),                         inline=True)
    embed.add_field(name="🌍 Locale",       value=str(g.preferred_locale),                   inline=True)
    embed.add_field(name="🔒 Verification", value=str(g.verification_level),                 inline=True)
    embed.add_field(name="🆔 Server ID",    value=str(g.id),                                 inline=True)
    if g.description:
        embed.description = g.description
    if g.banner:
        embed.set_image(url=g.banner.url)
    await ctx.reply(embed=embed)

# ── REVIEWPANEL ──────────────────────────────────────────────────
@bot.command(name="reviewpanel", aliases=["cbpanel", "cbr"])
@mod_check()
async def prefix_reviewpanel(ctx, target=None):
    if not target:
        return await ctx.reply(embed=error_embed("Missing User", "Provide a user."))
    user, _ = await resolve_user(ctx.guild, target)
    if not user:
        return await ctx.reply(embed=error_embed("User Not Found", "Could not find that user."))
    chatban = db_get_chatban(ctx.guild.id, user.id)
    warns   = db_get_warnings(ctx.guild.id, user.id)
    embed = discord.Embed(title="🔍 Chatban Review Panel", color=COLORS["mod"],
                          timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="User",          value=f"{user} (`{user.id}`)",                            inline=False)
    embed.add_field(name="Status",        value="🔴 Currently Chatbanned" if chatban else "🟢 Not Chatbanned", inline=True)
    embed.add_field(name="Warnings",      value=str(len(warns)),                                    inline=True)
    embed.add_field(name="Chatban Reason",value=chatban.get("reason", "N/A") if chatban else "N/A", inline=False)
    if chatban:
        applied_ts = int(datetime.fromisoformat(chatban["appliedAt"]).timestamp())
        embed.add_field(name="Applied", value=f"<t:{applied_ts}:R>", inline=True)
        if chatban.get("expiresAt"):
            exp_ts = int(datetime.fromisoformat(chatban["expiresAt"]).timestamp())
            embed.add_field(name="Expires", value=f"<t:{exp_ts}:R>", inline=True)
        else:
            embed.add_field(name="Expires", value="Permanent", inline=True)
    view = ReviewPanelView(user.id)
    await ctx.reply(embed=embed, view=view)

# ── HELP ─────────────────────────────────────────────────────────
@bot.command(name="help", aliases=["h", "commands"])
async def prefix_help(ctx):
    embed = discord.Embed(
        title="📚 Moderation Bot Commands",
        description="Prefix: `.` or `?` — All commands also available as `/command`",
        color=COLORS["info"], timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="⚠️ Warnings",
        value="`warn <user> [reason]` • `warnings <user>` • `delwarn <user> <id>`", inline=False)
    embed.add_field(name="🔇 Chat Restrictions",
        value="`chatban <user> [reason]` • `unchatban <user>`\n`mute <user> <duration> [reason]` • `unmute <user>`", inline=False)
    embed.add_field(name="🔨 Moderation",
        value="`kick <user> [reason]` • `ban <user> [reason]` • `unban <id> [reason]`", inline=False)
    embed.add_field(name="🔍 Information",
        value="`usercheck <user>` • `avatar [user]` • `serverinfo`\n`note <user> <text>` • `notes <user>` • `delnote <user> <id>`", inline=False)
    embed.add_field(name="📢 Channel Management",
        value="`lock` • `unlock` • `lockdown` • `unlockall` • `nuke`\n`slowmode <seconds>` • `purge <amount>`", inline=False)
    embed.add_field(name="🛡️ User Management",
        value="`nickname <user> [name]` • `role <user> <role>`", inline=False)
    embed.add_field(name="🚫 Filter",
        value="`filter add <word>` • `filter remove <word>` • `filter list`", inline=False)
    embed.add_field(name="⚙️ Config",
        value="`logschannel <#channel>` • `reviewpanel <user>`", inline=False)
    embed.set_footer(text="Duration format: 10m, 1h, 2d, 1w")
    await ctx.reply(embed=embed)

# ════════════════════════════════════════════════════════════════
#  REVIEW PANEL BUTTONS (View)
# ════════════════════════════════════════════════════════════════
class ReviewPanelView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    async def _check_perm(self, interaction: discord.Interaction) -> bool:
        if not has_mod_permission(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬆ Increase Ban", style=discord.ButtonStyle.danger,  custom_id="cbr_increase")
    async def increase(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perm(interaction): return
        await interaction.response.defer()
        existing = db_get_chatban(interaction.guild.id, self.user_id)
        if existing:
            existing["expiresAt"] = None
            db_set_chatban(interaction.guild.id, self.user_id, existing)
        else:
            await apply_chatban(interaction.guild, self.user_id, "Review panel: increased", interaction.user.id)
        user = await bot.fetch_user(self.user_id)
        await interaction.followup.send(embed=warn_embed("Ban Increased", f"{user}'s chatban has been made permanent."))

    @discord.ui.button(label="⬇ Decrease Ban", style=discord.ButtonStyle.primary, custom_id="cbr_decrease")
    async def decrease(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perm(interaction): return
        await interaction.response.defer()
        existing = db_get_chatban(interaction.guild.id, self.user_id)
        if existing:
            existing["expiresAt"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            db_set_chatban(interaction.guild.id, self.user_id, existing)
        user = await bot.fetch_user(self.user_id)
        await interaction.followup.send(embed=success_embed("Ban Decreased", f"{user}'s chatban reduced to 1 day."))

    @discord.ui.button(label="🔓 Remove Ban",   style=discord.ButtonStyle.success, custom_id="cbr_remove")
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perm(interaction): return
        await interaction.response.defer()
        await remove_chatban(interaction.guild, self.user_id)
        db_add_mod_action(interaction.guild.id, self.user_id,
                          {"type": "UNCHATBAN", "moderatorId": str(interaction.user.id), "reason": "Review panel: removed"})
        user = await bot.fetch_user(self.user_id)
        await interaction.followup.send(embed=success_embed("Chatban Removed", f"{user}'s chatban has been lifted."))
        await send_log(interaction.guild,
                       mod_embed("Chatban Removed (Panel)", interaction.user, user, "Review panel decision"))

    @discord.ui.button(label="✅ Keep As-Is",   style=discord.ButtonStyle.secondary, custom_id="cbr_keep")
    async def keep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_perm(interaction): return
        await interaction.response.defer()
        user = await bot.fetch_user(self.user_id)
        await interaction.followup.send(embed=info_embed("No Change", f"{user}'s chatban has been kept as-is."), ephemeral=True)

# ════════════════════════════════════════════════════════════════
#  SLASH COMMANDS
# ════════════════════════════════════════════════════════════════
guild_obj = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None

@bot.tree.command(name="warn", description="Warn a user", guild=guild_obj)
@app_commands.describe(user="User to warn", reason="Reason for the warning")
async def slash_warn(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    await do_warn(interaction.guild, interaction.user, str(user.id), reason,
                  lambda **kw: interaction.followup.send(**kw))

@bot.tree.command(name="warnings", description="View warnings for a user", guild=guild_obj)
@app_commands.describe(user="User to check")
async def slash_warnings(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    warns = db_get_warnings(interaction.guild.id, user.id)
    if not warns:
        return await interaction.followup.send(embed=info_embed("No Warnings", f"{user} has no warnings."))
    desc = "\n\n".join(
        f"**#{i+1}** • <t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:R>\n> {w['reason']}\n> *by <@{w['moderatorId']}>* • ID: `{w['id']}`"
        for i, w in enumerate(warns)
    )
    embed = discord.Embed(title=f"⚠️ Warnings for {user}", description=desc,
                          color=COLORS["warn"], timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f"{len(warns)} total warning(s)")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="delwarn", description="Delete a warning", guild=guild_obj)
@app_commands.describe(user="User", warning_id="Warning ID to delete")
async def slash_delwarn(interaction: discord.Interaction, user: discord.Member, warning_id: str):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    try:
        wid = int(warning_id)
    except ValueError:
        return await interaction.followup.send(embed=error_embed("Invalid ID", "Provide a valid warning ID."))
    removed = db_remove_warning(interaction.guild.id, user.id, wid)
    await interaction.followup.send(embed=success_embed("Warning Removed", f"Removed warning `{wid}` from {user}.") if removed
                                    else error_embed("Not Found", "Warning ID not found."))

@bot.tree.command(name="chatban", description="Chatban a user", guild=guild_obj)
@app_commands.describe(user="User to chatban", reason="Reason")
async def slash_chatban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    await apply_chatban(interaction.guild, user.id, reason, interaction.user.id)
    db_add_mod_action(interaction.guild.id, user.id, {"type": "CHATBAN", "moderatorId": str(interaction.user.id), "reason": reason})
    embed = mod_embed("Chatban Applied", interaction.user, user, reason)
    await send_log(interaction.guild, embed)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="unchatban", description="Remove a chatban", guild=guild_obj)
@app_commands.describe(user="User to unchatban")
async def slash_unchatban(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    await remove_chatban(interaction.guild, user.id)
    db_add_mod_action(interaction.guild.id, user.id, {"type": "UNCHATBAN", "moderatorId": str(interaction.user.id)})
    embed = mod_embed("Chatban Removed", interaction.user, user, "Chatban lifted")
    await send_log(interaction.guild, embed)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="mute", description="Timeout/mute a user", guild=guild_obj)
@app_commands.describe(user="User to mute", duration="Duration e.g. 10m, 1h, 2d", reason="Reason")
async def slash_mute(interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = "No reason provided"):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    await do_mute(interaction.guild, interaction.user, str(user.id), duration, reason,
                  lambda **kw: interaction.followup.send(**kw))

@bot.tree.command(name="unmute", description="Remove a timeout from a user", guild=guild_obj)
@app_commands.describe(user="User to unmute")
async def slash_unmute(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    try:
        await user.timeout(None, reason="Mute removed")
    except Exception as e:
        return await interaction.followup.send(embed=error_embed("Failed", str(e)))
    db_add_mod_action(interaction.guild.id, user.id, {"type": "UNMUTE", "moderatorId": str(interaction.user.id)})
    embed = mod_embed("Member Unmuted", interaction.user, user, "Mute removed")
    await send_log(interaction.guild, embed)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="kick", description="Kick a member", guild=guild_obj)
@app_commands.describe(user="User to kick", reason="Reason")
async def slash_kick(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Kick Members permission."), ephemeral=True)
    await interaction.response.defer()
    await do_kick(interaction.guild, interaction.user, str(user.id), reason,
                  lambda **kw: interaction.followup.send(**kw))

@bot.tree.command(name="ban", description="Ban a user", guild=guild_obj)
@app_commands.describe(user="User to ban", reason="Reason")
async def slash_ban(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Ban Members permission."), ephemeral=True)
    await interaction.response.defer()
    await do_ban(interaction.guild, interaction.user, str(user.id), reason,
                 lambda **kw: interaction.followup.send(**kw))

@bot.tree.command(name="unban", description="Unban a user by ID", guild=guild_obj)
@app_commands.describe(user_id="User ID to unban", reason="Reason")
async def slash_unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Ban Members permission."), ephemeral=True)
    await interaction.response.defer()
    try:
        ban_entry = await interaction.guild.fetch_ban(discord.Object(id=int(user_id)))
    except discord.NotFound:
        return await interaction.followup.send(embed=error_embed("Not Banned", "That user is not banned."))
    await interaction.guild.unban(ban_entry.user, reason=reason)
    db_add_mod_action(interaction.guild.id, ban_entry.user.id, {"type": "UNBAN", "moderatorId": str(interaction.user.id), "reason": reason})
    embed = mod_embed("Member Unbanned", interaction.user, ban_entry.user, reason)
    await send_log(interaction.guild, embed)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="usercheck", description="View user info and mod history", guild=guild_obj)
@app_commands.describe(user="User to check")
async def slash_usercheck(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    warns   = db_get_warnings(interaction.guild.id, user.id)
    actions = db_get_mod_actions(interaction.guild.id, user.id)
    age     = account_age_days(user)
    embed = discord.Embed(title=f"🔍 User Check: {user}", color=COLORS["info"],
                          timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User",            value=f"{user.mention} (`{user.id}`)",                 inline=True)
    embed.add_field(name="📅 Account Created", value=f"<t:{int(user.created_at.timestamp())}:R>",     inline=True)
    embed.add_field(name="📆 Account Age",     value=f"{age} days {'⚠️ NEW' if age < 7 else ''}",    inline=True)
    embed.add_field(name="📥 Joined Server",   value=f"<t:{int(user.joined_at.timestamp())}:R>",      inline=True)
    roles = [r.mention for r in user.roles if r.id != interaction.guild.id]
    embed.add_field(name="🏷️ Roles", value=", ".join(roles) or "None", inline=False)
    warn_val = "\n".join(
        f"• {w['reason']} — <t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:R>"
        for w in warns[-3:]
    ) if warns else "None"
    embed.add_field(name=f"⚠️ Warnings ({len(warns)})", value=warn_val, inline=False)
    action_val = "\n".join(
        f"• **{a['type']}** — {a.get('reason','')} <t:{int(datetime.fromisoformat(a['timestamp']).timestamp())}:R>"
        for a in actions[-5:]
    ) if actions else "None"
    embed.add_field(name=f"🔨 Recent Actions ({len(actions)})", value=action_val, inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="note", description="Add a private mod note to a user", guild=guild_obj)
@app_commands.describe(user="User", text="Note text")
async def slash_note(interaction: discord.Interaction, user: discord.Member, text: str):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    entry = db_add_note(interaction.guild.id, user.id, interaction.user.id, text)
    await interaction.followup.send(embed=success_embed("Note Added",
        f"Note added for {user}.\n> {text}\nID: `{entry['id']}`"))

@bot.tree.command(name="notes", description="View notes for a user", guild=guild_obj)
@app_commands.describe(user="User")
async def slash_notes(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    notes = db_get_notes(interaction.guild.id, user.id)
    if not notes:
        return await interaction.followup.send(embed=info_embed("No Notes", f"No notes for {user}."))
    desc = "\n\n".join(
        f"**#{i+1}** by <@{n['moderatorId']}> • <t:{int(datetime.fromisoformat(n['timestamp']).timestamp())}:R>\n> {n['note']}\n> ID: `{n['id']}`"
        for i, n in enumerate(notes)
    )
    await interaction.followup.send(embed=discord.Embed(title=f"📝 Notes for {user}", description=desc,
                                                         color=COLORS["info"], timestamp=datetime.now(timezone.utc)))

@bot.tree.command(name="delnote", description="Delete a note", guild=guild_obj)
@app_commands.describe(user="User", note_id="Note ID")
async def slash_delnote(interaction: discord.Interaction, user: discord.Member, note_id: str):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    removed = db_remove_note(interaction.guild.id, user.id, int(note_id))
    await interaction.followup.send(embed=success_embed("Note Deleted", "Note removed.") if removed
                                    else error_embed("Not Found", "Note ID not found."))

@bot.tree.command(name="lock", description="Lock the current channel", guild=guild_obj)
async def slash_lock(interaction: discord.Interaction):
    if not has_admin_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Guild permission."), ephemeral=True)
    await interaction.response.defer()
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.followup.send(embed=success_embed("Channel Locked", f"{interaction.channel.mention} is now locked."))

@bot.tree.command(name="unlock", description="Unlock the current channel", guild=guild_obj)
async def slash_unlock(interaction: discord.Interaction):
    if not has_admin_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Guild permission."), ephemeral=True)
    await interaction.response.defer()
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
    await interaction.followup.send(embed=success_embed("Channel Unlocked", f"{interaction.channel.mention} is now unlocked."))

@bot.tree.command(name="lockdown", description="Lock all channels", guild=guild_obj)
async def slash_lockdown(interaction: discord.Interaction):
    if not has_admin_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Guild permission."), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            await ch.set_permissions(interaction.guild.default_role, send_messages=False)
            count += 1
        except Exception:
            pass
    await interaction.followup.send(embed=warn_embed("Lockdown Active", f"Locked **{count}** channels."))

@bot.tree.command(name="unlockall", description="Unlock all channels", guild=guild_obj)
async def slash_unlockall(interaction: discord.Interaction):
    if not has_admin_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Guild permission."), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            await ch.set_permissions(interaction.guild.default_role, send_messages=None)
            count += 1
        except Exception:
            pass
    await interaction.followup.send(embed=success_embed("Lockdown Lifted", f"Unlocked **{count}** channels."))

@bot.tree.command(name="nuke", description="Clone and delete current channel", guild=guild_obj)
async def slash_nuke(interaction: discord.Interaction):
    if not has_admin_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Guild permission."), ephemeral=True)
    await interaction.response.defer()
    channel = interaction.channel
    new_ch = await channel.clone(name=channel.name, reason="Nuke command")
    await new_ch.edit(position=channel.position)
    await channel.delete(reason="Nuked")
    await new_ch.send(embed=success_embed("Channel Nuked", "💣 Channel has been nuked and recreated."))

@bot.tree.command(name="nickname", description="Force change a user's nickname", guild=guild_obj)
@app_commands.describe(user="User", nickname="New nickname (leave empty to reset)")
async def slash_nickname(interaction: discord.Interaction, user: discord.Member, nickname: str = None):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    await user.edit(nick=nickname, reason=f"Changed by {interaction.user}")
    await interaction.followup.send(embed=success_embed("Nickname Changed",
        f"{user.mention}'s nickname set to: **{nickname or '(reset)'}**"))

@bot.tree.command(name="role", description="Add or remove a role from a user", guild=guild_obj)
@app_commands.describe(user="User", role="Role to add/remove")
async def slash_role(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not has_admin_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Guild permission."), ephemeral=True)
    await interaction.response.defer()
    if role in user.roles:
        await user.remove_roles(role)
        await interaction.followup.send(embed=success_embed("Role Removed", f"Removed {role.mention} from {user}."))
    else:
        await user.add_roles(role)
        await interaction.followup.send(embed=success_embed("Role Added", f"Added {role.mention} to {user}."))

@bot.tree.command(name="purge", description="Bulk delete messages", guild=guild_obj)
@app_commands.describe(amount="Number of messages (1–100)")
async def slash_purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100] = 10):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Messages permission."), ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(embed=success_embed("Purge Complete", f"Deleted **{len(deleted)}** messages."), ephemeral=True)

@bot.tree.command(name="slowmode", description="Set channel slowmode", guild=guild_obj)
@app_commands.describe(seconds="Seconds (0 to disable)")
async def slash_slowmode(interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600] = 0):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.followup.send(embed=success_embed("Slowmode Set",
        "Slowmode disabled." if seconds == 0 else f"Slowmode set to **{seconds}s**."))

@bot.tree.command(name="avatar", description="Show a user's avatar", guild=guild_obj)
@app_commands.describe(user="User (defaults to yourself)")
async def slash_avatar(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer()
    u = user or interaction.user
    embed = discord.Embed(title=f"🖼️ {u}'s Avatar", color=COLORS["info"],
                          timestamp=datetime.now(timezone.utc))
    embed.set_image(url=u.display_avatar.url)
    png  = u.display_avatar.replace(format="png",  size=1024).url
    webp = u.display_avatar.replace(format="webp", size=1024).url
    jpg  = u.display_avatar.replace(format="jpg",  size=1024).url
    embed.description = f"[PNG]({png}) | [WebP]({webp}) | [JPG]({jpg})"
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="logschannel", description="Set the mod logs channel", guild=guild_obj)
@app_commands.describe(channel="Channel for mod logs")
async def slash_logschannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_admin_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need Manage Guild permission."), ephemeral=True)
    await interaction.response.defer()
    db_set_config(interaction.guild.id, "logsChannelId", str(channel.id))
    await interaction.followup.send(embed=success_embed("Logs Channel Set", f"All mod logs will be sent to {channel.mention}."))

@bot.tree.command(name="serverinfo", description="Show server information", guild=guild_obj)
async def slash_serverinfo(interaction: discord.Interaction):
    await interaction.response.defer()
    g = interaction.guild
    embed = discord.Embed(title=f"📊 {g.name}", color=COLORS["info"],
                          timestamp=datetime.now(timezone.utc))
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="👑 Owner",        value=f"<@{g.owner_id}>",                       inline=True)
    embed.add_field(name="📅 Created",      value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="👥 Members",      value=str(g.member_count),                      inline=True)
    embed.add_field(name="💬 Channels",     value=str(len(g.channels)),                     inline=True)
    embed.add_field(name="🎭 Roles",        value=str(len(g.roles)),                        inline=True)
    embed.add_field(name="🔒 Verification", value=str(g.verification_level),                inline=True)
    embed.add_field(name="🆔 Server ID",    value=str(g.id),                                inline=True)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="reviewpanel", description="Open chatban review panel for a user", guild=guild_obj)
@app_commands.describe(user="User to review")
async def slash_reviewpanel(interaction: discord.Interaction, user: discord.Member):
    if not has_mod_permission(interaction.user):
        return await interaction.response.send_message(embed=error_embed("No Permission", "You need moderation permissions."), ephemeral=True)
    await interaction.response.defer()
    chatban = db_get_chatban(interaction.guild.id, user.id)
    warns   = db_get_warnings(interaction.guild.id, user.id)
    embed = discord.Embed(title="🔍 Chatban Review Panel", color=COLORS["mod"],
                          timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="User",    value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="Status",  value="🔴 Currently Chatbanned" if chatban else "🟢 Not Chatbanned", inline=True)
    embed.add_field(name="Warnings",value=str(len(warns)), inline=True)
    embed.add_field(name="Chatban Reason", value=chatban.get("reason", "N/A") if chatban else "N/A", inline=False)
    view = ReviewPanelView(user.id)
    await interaction.followup.send(embed=embed, view=view)

@bot.tree.command(name="help", description="Show all commands", guild=guild_obj)
async def slash_help(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(
        title="📚 Moderation Bot Commands",
        description="Prefix: `.` or `?` — All commands also available as `/command`",
        color=COLORS["info"], timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="⚠️ Warnings",
        value="`warn <user> [reason]` • `warnings <user>` • `delwarn <user> <id>`", inline=False)
    embed.add_field(name="🔇 Chat Restrictions",
        value="`chatban <user> [reason]` • `unchatban <user>`\n`mute <user> <duration> [reason]` • `unmute <user>`", inline=False)
    embed.add_field(name="🔨 Moderation",
        value="`kick <user> [reason]` • `ban <user> [reason]` • `unban <id> [reason]`", inline=False)
    embed.add_field(name="🔍 Information",
        value="`usercheck <user>` • `avatar [user]` • `serverinfo`\n`note <user> <text>` • `notes <user>` • `delnote <user> <id>`", inline=False)
    embed.add_field(name="📢 Channel Management",
        value="`lock` • `unlock` • `lockdown` • `unlockall` • `nuke`\n`slowmode <seconds>` • `purge <amount>`", inline=False)
    embed.add_field(name="🛡️ User Management",
        value="`nickname <user> [name]` • `role <user> <role>`", inline=False)
    embed.add_field(name="🚫 Filter",
        value="`filter add <word>` • `filter remove <word>` • `filter list`", inline=False)
    embed.add_field(name="⚙️ Config",
        value="`logschannel <#channel>` • `reviewpanel <user>`", inline=False)
    embed.set_footer(text="Duration format: 10m, 1h, 2d, 1w")
    await interaction.followup.send(embed=embed)

# ════════════════════════════════════════════════════════════════
#  RUN
# ════════════════════════════════════════════════════════════════
bot.run(TOKEN)
