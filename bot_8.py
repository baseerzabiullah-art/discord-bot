import discord
from discord.ext import commands
from discord import app_commands
import os, json, time, datetime
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
PREFIXES = ['.', '?']
WELCOME_GIF = 'https://media1.tenor.com/m/MSD7y-yu1oMAAAAC/hola-pocoyo.gif'
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

TICKET_CATEGORIES = {
    'support':  {'label': '🛠️ Support',         'description': 'Get help with a technical issue',     'color': 0x5865F2},
    'purchase': {'label': '💳 Buy Sparky AI',    'description': 'Purchase or enquire about Sparky AI', 'color': 0x57F287},
    'general':  {'label': '💬 General Question', 'description': 'Ask us anything',                     'color': 0xFEE75C},
}

# ═══════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════
def _load(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path): return {}
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def _save(filename, data):
    with open(os.path.join(DATA_DIR, filename), 'w') as f:
        json.dump(data, f, indent=2)

def get_warnings(guild_id, user_id):
    return _load('warnings.json').get(str(guild_id), {}).get(str(user_id), [])

def add_warning(guild_id, user_id, moderator_id, reason):
    data = _load('warnings.json')
    gid, uid = str(guild_id), str(user_id)
    data.setdefault(gid, {}).setdefault(uid, [])
    data[gid][uid].append({'id': int(time.time()*1000), 'moderator_id': str(moderator_id), 'reason': reason, 'timestamp': _now()})
    _save('warnings.json', data)
    return data[gid][uid]

def remove_warning(guild_id, user_id, warning_id):
    data = _load('warnings.json')
    gid, uid = str(guild_id), str(user_id)
    if gid not in data or uid not in data[gid]: return False
    before = len(data[gid][uid])
    data[gid][uid] = [w for w in data[gid][uid] if w['id'] != warning_id]
    _save('warnings.json', data)
    return len(data[gid][uid]) < before

def get_mod_actions(guild_id, user_id):
    return _load('modactions.json').get(str(guild_id), {}).get(str(user_id), [])

def add_mod_action(guild_id, user_id, action):
    data = _load('modactions.json')
    gid, uid = str(guild_id), str(user_id)
    data.setdefault(gid, {}).setdefault(uid, [])
    action['timestamp'] = _now()
    data[gid][uid].append(action)
    _save('modactions.json', data)

def get_notes(guild_id, user_id):
    return _load('notes.json').get(str(guild_id), {}).get(str(user_id), [])

def add_note(guild_id, user_id, moderator_id, note):
    data = _load('notes.json')
    gid, uid = str(guild_id), str(user_id)
    data.setdefault(gid, {}).setdefault(uid, [])
    entry = {'id': int(time.time()*1000), 'moderator_id': str(moderator_id), 'note': note, 'timestamp': _now()}
    data[gid][uid].append(entry)
    _save('notes.json', data)
    return entry

def remove_note(guild_id, user_id, note_id):
    data = _load('notes.json')
    gid, uid = str(guild_id), str(user_id)
    if gid not in data or uid not in data[gid]: return False
    before = len(data[gid][uid])
    data[gid][uid] = [n for n in data[gid][uid] if n['id'] != note_id]
    _save('notes.json', data)
    return len(data[gid][uid]) < before

def get_config(guild_id):
    return _load('config.json').get(str(guild_id), {})

def set_config(guild_id, key, value):
    data = _load('config.json')
    data.setdefault(str(guild_id), {})[key] = value
    _save('config.json', data)

def get_filter_words(guild_id):
    return _load('filter.json').get(str(guild_id), [])

def add_filter_word(guild_id, word):
    data = _load('filter.json')
    gid = str(guild_id)
    data.setdefault(gid, [])
    if word.lower() not in data[gid]:
        data[gid].append(word.lower())
        _save('filter.json', data)
        return True
    return False

def remove_filter_word(guild_id, word):
    data = _load('filter.json')
    gid = str(guild_id)
    if gid not in data: return False
    before = len(data[gid])
    data[gid] = [w for w in data[gid] if w != word.lower()]
    _save('filter.json', data)
    return len(data[gid]) < before

def set_chatban(guild_id, user_id, chatban_data):
    data = _load('chatbans.json')
    data.setdefault(str(guild_id), {})[str(user_id)] = chatban_data
    _save('chatbans.json', data)

def get_chatban(guild_id, user_id):
    return _load('chatbans.json').get(str(guild_id), {}).get(str(user_id))

def del_chatban(guild_id, user_id):
    data = _load('chatbans.json')
    gid, uid = str(guild_id), str(user_id)
    if gid in data and uid in data[gid]:
        del data[gid][uid]
        _save('chatbans.json', data)

def get_tickets(guild_id):
    return _load('tickets.json').get(str(guild_id), {})

def save_ticket(guild_id, channel_id, data):
    all_data = _load('tickets.json')
    all_data.setdefault(str(guild_id), {})[str(channel_id)] = data
    _save('tickets.json', all_data)

def delete_ticket_record(guild_id, channel_id):
    all_data = _load('tickets.json')
    gid = str(guild_id)
    if gid in all_data and str(channel_id) in all_data[gid]:
        del all_data[gid][str(channel_id)]
        _save('tickets.json', all_data)

# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════
def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

COLORS = {'success': 0x57F287, 'error': 0xED4245, 'warn': 0xFEE75C, 'info': 0x5865F2, 'mod': 0xEB459E}

def success_embed(title, desc):
    return discord.Embed(title=f'✅ {title}', description=desc, color=COLORS['success'])

def error_embed(title, desc):
    return discord.Embed(title=f'❌ {title}', description=desc, color=COLORS['error'])

def warn_embed(title, desc):
    return discord.Embed(title=f'⚠️ {title}', description=desc, color=COLORS['warn'])

def info_embed(title, desc):
    return discord.Embed(title=f'ℹ️ {title}', description=desc, color=COLORS['info'])

def mod_embed(action, moderator, target, reason, extra=None):
    e = discord.Embed(title=f'🔨 {action}', color=COLORS['mod'], timestamp=discord.utils.utcnow())
    e.add_field(name='Target', value=f'{target} (`{getattr(target, "id", target)}`)', inline=True)
    e.add_field(name='Moderator', value=str(moderator), inline=True)
    e.add_field(name='Reason', value=reason or 'No reason provided', inline=False)
    if extra:
        for k, v in extra.items(): e.add_field(name=k, value=str(v), inline=True)
    return e

def is_mod(member):
    p = member.guild_permissions
    return any([p.moderate_members, p.ban_members, p.kick_members, p.administrator])

def is_admin(member):
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild

def age_days(user):
    return (discord.utils.utcnow() - user.created_at).days

def parse_duration(s):
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
    if not s or s[-1] not in units: return None
    try:
        v = int(s[:-1])
        secs = v * units[s[-1]]
        return secs if secs <= 28*86400 else None
    except: return None

async def send_log(guild, embed):
    cfg = get_config(guild.id)
    ch_id = cfg.get('logsChannelId')
    if ch_id:
        ch = guild.get_channel(int(ch_id))
        if ch:
            try: await ch.send(embed=embed)
            except: pass

async def do_reply(ctx_or_inter, **kwargs):
    if isinstance(ctx_or_inter, commands.Context):
        await ctx_or_inter.reply(**kwargs)
    else:
        if ctx_or_inter.response.is_done():
            await ctx_or_inter.followup.send(**kwargs)
        else:
            await ctx_or_inter.response.send_message(**kwargs)

async def apply_chatban(guild, user_id, reason, mod_id, duration_secs=None):
    member = guild.get_member(int(user_id))
    if not member: return False
    for ch in guild.text_channels:
        try:
            await ch.set_permissions(member, send_messages=False, add_reactions=False,
                                     create_public_threads=False, create_private_threads=False,
                                     send_messages_in_threads=False)
        except: pass
    set_chatban(guild.id, user_id, {
        'moderator_id': str(mod_id), 'reason': reason, 'applied_at': _now(),
        'expires_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + duration_secs)) if duration_secs else None
    })
    return True

async def remove_chatban(guild, user_id):
    member = guild.get_member(int(user_id))
    if member:
        for ch in guild.text_channels:
            try:
                ow = ch.overwrites_for(member)
                ow.send_messages = None
                ow.add_reactions = None
                ow.create_public_threads = None
                ow.create_private_threads = None
                ow.send_messages_in_threads = None
                if ow.is_empty():
                    await ch.set_permissions(member, overwrite=None)
                else:
                    await ch.set_permissions(member, overwrite=ow)
            except: pass
    del_chatban(guild.id, user_id)

# ═══════════════════════════════════════════════════════════════
#  TRANSCRIPT HELPER
# ═══════════════════════════════════════════════════════════════
async def send_transcript(guild, ticket_channel, ticket_data):
    """Collect all messages from ticket channel and post transcript."""
    cfg = get_config(guild.id)
    transcript_ch_id = cfg.get('transcriptChannelId')
    if not transcript_ch_id:
        return

    transcript_ch = guild.get_channel(int(transcript_ch_id))
    if not transcript_ch:
        return

    # Collect messages oldest first
    messages = []
    try:
        async for msg in ticket_channel.history(limit=500, oldest_first=True):
            if msg.author.bot and not msg.embeds:
                continue
            messages.append(msg)
    except:
        return

    cat_info = TICKET_CATEGORIES.get(ticket_data.get('type', 'general'), TICKET_CATEGORIES['general'])
    ticket_number = ticket_data.get('number', '?')
    opener_id = ticket_data.get('user_id', '?')
    opened_at = ticket_data.get('opened_at', 'Unknown')
    closed_at = ticket_data.get('closed_at', _now())
    closed_by_id = ticket_data.get('closed_by', '?')

    # Build transcript text
    lines = []
    lines.append(f'TICKET TRANSCRIPT — #{ticket_number:04d}' if isinstance(ticket_number, int) else f'TICKET TRANSCRIPT — #{ticket_number}')
    lines.append(f'Type     : {cat_info["label"]}')
    lines.append(f'Opened by: {opener_id}')
    lines.append(f'Opened at: {opened_at}')
    lines.append(f'Closed by: {closed_by_id}')
    lines.append(f'Closed at: {closed_at}')
    lines.append(f'Messages : {len(messages)}')
    lines.append('=' * 60)
    lines.append('')

    for msg in messages:
        ts = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
        content = msg.content or ''
        if msg.embeds:
            for emb in msg.embeds:
                title = emb.title or ''
                desc = emb.description or ''
                content += f'[Embed: {title} — {desc[:100]}]'
        if msg.attachments:
            for att in msg.attachments:
                content += f' [Attachment: {att.url}]'
        lines.append(f'[{ts}] {msg.author.display_name} ({msg.author.id}): {content}')

    transcript_text = '\n'.join(lines)

    # Send as a file attachment if long, otherwise in an embed
    transcript_embed = discord.Embed(
        title=f'📋 Ticket Transcript — #{ticket_number:04d}' if isinstance(ticket_number, int) else f'📋 Ticket Transcript — #{ticket_number}',
        color=cat_info['color'],
        timestamp=discord.utils.utcnow()
    )
    transcript_embed.add_field(name='📋 Type',      value=cat_info['label'],          inline=True)
    transcript_embed.add_field(name='👤 Opened by', value=f'<@{opener_id}>',          inline=True)
    transcript_embed.add_field(name='🔒 Closed by', value=f'<@{closed_by_id}>',       inline=True)
    transcript_embed.add_field(name='📅 Opened',    value=opened_at,                  inline=True)
    transcript_embed.add_field(name='📅 Closed',    value=closed_at,                  inline=True)
    transcript_embed.add_field(name='💬 Messages',  value=str(len(messages)),         inline=True)
    transcript_embed.set_footer(text=f'Channel: {ticket_channel.name}')

    # Send as .txt file attachment
    import io
    file = discord.File(
        fp=io.BytesIO(transcript_text.encode('utf-8')),
        filename=f'transcript-{ticket_channel.name}.txt'
    )

    try:
        await transcript_ch.send(embed=transcript_embed, file=file)
    except:
        pass

# ═══════════════════════════════════════════════════════════════
#  BOT SETUP
# ═══════════════════════════════════════════════════════════════
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.moderation = True

bot = commands.Bot(command_prefix=PREFIXES, intents=intents, help_command=None)
tree = bot.tree
spam_map = {}

# ═══════════════════════════════════════════════════════════════
#  TICKET VIEWS
# ═══════════════════════════════════════════════════════════════
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='ticket_close')
    async def close_ticket(self, inter: discord.Interaction, button: discord.ui.Button):
        ticket_data = get_tickets(inter.guild.id).get(str(inter.channel.id))
        if not ticket_data:
            return await inter.response.send_message(embed=error_embed('Error', 'This is not a tracked ticket.'), ephemeral=True)
        is_owner = str(inter.user.id) == str(ticket_data.get('user_id'))
        if not is_owner and not is_mod(inter.guild.get_member(inter.user.id)):
            return await inter.response.send_message(embed=error_embed('No Permission', 'Only the ticket owner or staff can close this.'), ephemeral=True)
        await inter.response.defer()

        ticket_data['open'] = False
        ticket_data['closed_at'] = _now()
        ticket_data['closed_by'] = str(inter.user.id)
        save_ticket(inter.guild.id, inter.channel.id, ticket_data)

        # Save transcript BEFORE deleting the channel
        await send_transcript(inter.guild, inter.channel, ticket_data)

        embed = discord.Embed(
            title='🔒 Ticket Closing',
            description='This ticket will be deleted in **5 seconds**.\n📋 Transcript has been saved.',
            color=COLORS['error'],
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name='Closed by', value=inter.user.mention)
        await inter.channel.send(embed=embed)

        cat_info = TICKET_CATEGORIES.get(ticket_data.get('type', 'general'), TICKET_CATEGORIES['general'])
        log_embed = discord.Embed(title='🎫 Ticket Closed', color=COLORS['mod'], timestamp=discord.utils.utcnow())
        log_embed.add_field(name='Channel', value=inter.channel.name, inline=True)
        log_embed.add_field(name='Opened by', value=f'<@{ticket_data["user_id"]}>', inline=True)
        log_embed.add_field(name='Closed by', value=inter.user.mention, inline=True)
        log_embed.add_field(name='Type', value=cat_info['label'], inline=True)
        await send_log(inter.guild, log_embed)

        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        try:
            await inter.channel.delete(reason=f'Ticket closed by {inter.user}')
            delete_ticket_record(inter.guild.id, inter.channel.id)
        except: pass

    @discord.ui.button(label='👋 Claim', style=discord.ButtonStyle.primary, custom_id='ticket_claim')
    async def claim_ticket(self, inter: discord.Interaction, button: discord.ui.Button):
        if not is_mod(inter.guild.get_member(inter.user.id)):
            return await inter.response.send_message(embed=error_embed('No Permission', 'Only staff can claim tickets.'), ephemeral=True)
        ticket_data = get_tickets(inter.guild.id).get(str(inter.channel.id))
        if not ticket_data:
            return await inter.response.send_message(embed=error_embed('Error', 'This is not a tracked ticket.'), ephemeral=True)
        if ticket_data.get('claimed_by'):
            claimer = inter.guild.get_member(int(ticket_data['claimed_by']))
            return await inter.response.send_message(embed=warn_embed('Already Claimed', f'This ticket is already claimed by {claimer.mention if claimer else "someone"}.'), ephemeral=True)
        ticket_data['claimed_by'] = str(inter.user.id)
        save_ticket(inter.guild.id, inter.channel.id, ticket_data)
        await inter.response.send_message(embed=success_embed('Ticket Claimed', f'{inter.user.mention} has claimed this ticket and will assist you shortly.'))
        button.label = f'✅ Claimed by {inter.user.display_name}'
        button.disabled = True
        await inter.message.edit(view=self)

    @discord.ui.button(label='➕ Add User', style=discord.ButtonStyle.secondary, custom_id='ticket_adduser')
    async def add_user(self, inter: discord.Interaction, button: discord.ui.Button):
        if not is_mod(inter.guild.get_member(inter.user.id)):
            return await inter.response.send_message(embed=error_embed('No Permission', 'Only staff can add users.'), ephemeral=True)
        await inter.response.send_modal(AddUserModal(inter.channel))


class AddUserModal(discord.ui.Modal, title='Add User to Ticket'):
    user_id = discord.ui.TextInput(label='User ID or mention', placeholder='123456789012345678')

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, inter: discord.Interaction):
        cleaned = self.user_id.value.strip().replace('<@', '').replace('>', '').replace('!', '')
        try:
            member = inter.guild.get_member(int(cleaned)) or await inter.guild.fetch_member(int(cleaned))
        except:
            return await inter.response.send_message(embed=error_embed('Not Found', 'Could not find that user.'), ephemeral=True)
        await self.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await inter.response.send_message(embed=success_embed('User Added', f'{member.mention} has been added to this ticket.'))


RULES_LINK = 'https://discord.com/channels/1507699367123877979/1508243878652936282'


async def _create_ticket_channel(inter: discord.Interaction, ticket_type: str, form_data: dict):
    """Actually creates the ticket channel. Called after pre-screening is complete."""
    guild = inter.guild
    user = inter.user
    cat_info = TICKET_CATEGORIES[ticket_type]
    existing_tickets = get_tickets(guild.id)

    ticket_category = discord.utils.get(guild.categories, name='Tickets')
    if not ticket_category:
        ticket_category = await guild.create_category('Tickets')

    ticket_number = len(existing_tickets) + 1
    channel_name = f'ticket-{ticket_number:04d}-{user.name[:12].lower().replace(" ", "-")}'

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
    }
    for role in guild.roles:
        if role.permissions.manage_messages or role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    ticket_ch = await ticket_category.create_text_channel(
        channel_name,
        overwrites=overwrites,
        topic=f'{cat_info["label"]} ticket by {user} | Type: {ticket_type}'
    )

    save_ticket(guild.id, ticket_ch.id, {
        'user_id': str(user.id),
        'type': ticket_type,
        'opened_at': _now(),
        'open': True,
        'number': ticket_number,
        'claimed_by': None
    })

    # Build description from form answers
    if ticket_type == 'support':
        description = (
            f'**Issue:**\n> {form_data.get("issue", "Not provided")}\n\n'
            f'**Resolution requested:**\n> {form_data.get("resolution", "Not provided")}\n\n'
            'A staff member will be with you shortly.'
        )
    elif ticket_type == 'general':
        description = (
            f'**Question:**\n> {form_data.get("question", "Not provided")}\n\n'
            f'**Additional context:**\n> {form_data.get("context", "Not provided")}\n\n'
            'A staff member will reply as soon as possible.'
        )
    else:
        description = (
            'Thanks for your interest in **Sparky AI**! 🎉\n\n'
            '> 🔹 Which plan are you interested in?\n'
            '> 🔹 Do you have any questions before purchasing?\n'
            '> 🔹 Looking for a custom or enterprise deal?\n\n'
            'A team member will be with you shortly.'
        )

    embed = discord.Embed(
        title=f'{cat_info["label"]} — Ticket #{ticket_number:04d}',
        description=description,
        color=cat_info['color'],
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name='👤 Opened by', value=user.mention, inline=True)
    embed.add_field(name='📋 Type', value=cat_info['label'], inline=True)
    embed.add_field(name='📅 Opened', value=discord.utils.format_dt(discord.utils.utcnow(), 'R'), inline=True)
    embed.set_footer(text='Use the buttons below to manage this ticket.')

    await ticket_ch.send(content=user.mention, embed=embed, view=TicketControlView())

    log_embed = discord.Embed(title='🎫 Ticket Opened', color=cat_info['color'], timestamp=discord.utils.utcnow())
    log_embed.add_field(name='User', value=f'{user.mention} (`{user.id}`)', inline=True)
    log_embed.add_field(name='Type', value=cat_info['label'], inline=True)
    log_embed.add_field(name='Channel', value=ticket_ch.mention, inline=True)
    await send_log(guild, log_embed)

    return ticket_ch


# ── Support form modal ───────────────────────────────────────────
class SupportFormModal(discord.ui.Modal, title='Support Ticket — Tell us more'):
    issue = discord.ui.TextInput(
        label='What is your issue?',
        style=discord.TextStyle.paragraph,
        placeholder='Describe your problem in as much detail as possible...',
        max_length=1000
    )
    resolution = discord.ui.TextInput(
        label='How can we resolve this?',
        style=discord.TextStyle.paragraph,
        placeholder='What outcome are you hoping for?',
        max_length=500
    )

    async def on_submit(self, inter: discord.Interaction):
        ticket_ch = await _create_ticket_channel(inter, 'support', {
            'issue': self.issue.value,
            'resolution': self.resolution.value
        })
        await inter.response.send_message(
            embed=success_embed('Ticket Created', f'Your support ticket has been opened: {ticket_ch.mention}'),
            ephemeral=True
        )


# ── General question form modal ──────────────────────────────────
class GeneralFormModal(discord.ui.Modal, title='General Question — Tell us more'):
    question = discord.ui.TextInput(
        label='What is your question?',
        style=discord.TextStyle.paragraph,
        placeholder='Be as specific as possible...',
        max_length=1000
    )
    context = discord.ui.TextInput(
        label='Any additional context?',
        style=discord.TextStyle.paragraph,
        placeholder='Include any relevant details that might help us answer...',
        max_length=500,
        required=False
    )

    async def on_submit(self, inter: discord.Interaction):
        ticket_ch = await _create_ticket_channel(inter, 'general', {
            'question': self.question.value,
            'context': self.context.value or 'None provided'
        })
        await inter.response.send_message(
            embed=success_embed('Ticket Created', f'Your ticket has been opened: {ticket_ch.mention}'),
            ephemeral=True
        )


# ── Rules check view (Yes / No buttons) ─────────────────────────
class RulesCheckView(discord.ui.View):
    def __init__(self, ticket_type: str):
        super().__init__(timeout=120)
        self.ticket_type = ticket_type

    @discord.ui.button(label='✅ Yes, I have read the rules', style=discord.ButtonStyle.success)
    async def yes_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        # Open the appropriate form modal
        if self.ticket_type == 'support':
            await inter.response.send_modal(SupportFormModal())
        else:
            await inter.response.send_modal(GeneralFormModal())

    @discord.ui.button(label='❌ No', style=discord.ButtonStyle.danger)
    async def no_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.edit_message(
            embed=error_embed(
                'Ticket Cancelled',
                f'Please read our rules before opening a ticket.\n\n'
                f'📖 **Rules channel:** {RULES_LINK}\n\n'
                f'Once you have read the rules, feel free to open a new ticket.'
            ),
            view=None
        )


class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label='🛠️ Support',         value='support',  description='Get help with a technical issue'),
            discord.SelectOption(label='💳 Buy Sparky AI',   value='purchase', description='Purchase or enquire about Sparky AI'),
            discord.SelectOption(label='💬 General Question', value='general',  description='Ask us anything'),
        ]
        super().__init__(placeholder='Choose a ticket type...', min_values=1, max_values=1, options=options, custom_id='ticket_type_select')

    async def callback(self, inter: discord.Interaction):
        ticket_type = self.values[0]
        guild = inter.guild
        user = inter.user

        # Check for existing open ticket
        existing_tickets = get_tickets(guild.id)
        for ch_id, tdata in existing_tickets.items():
            if str(tdata.get('user_id')) == str(user.id) and tdata.get('open'):
                ch = guild.get_channel(int(ch_id))
                if ch:
                    return await inter.response.send_message(
                        embed=error_embed('Ticket Already Open', f'You already have an open ticket: {ch.mention}'),
                        ephemeral=True
                    )

        # Purchase tickets skip pre-screening and open directly
        if ticket_type == 'purchase':
            await inter.response.defer(ephemeral=True)
            ticket_ch = await _create_ticket_channel(inter, 'purchase', {})
            await inter.followup.send(
                embed=success_embed('Ticket Created', f'Your ticket has been opened: {ticket_ch.mention}'),
                ephemeral=True
            )
            return

        # Support & General — show rules check first
        if ticket_type == 'support':
            pre_embed = discord.Embed(
                title='🛠️ Before you open a Support ticket...',
                description=(
                    f'**Have you read our rules?**\n'
                    f'👉 {RULES_LINK}\n\n'
                    f'Please make sure you have read our rules before opening a ticket. '
                    f'This helps us assist you faster and keeps things running smoothly.'
                ),
                color=COLORS['warn']
            )
            pre_embed.add_field(name='📋 You will be asked:', value='• What is your issue?\n• How can we resolve this?', inline=False)
            pre_embed.set_footer(text='This prompt will expire in 2 minutes.')
        else:
            pre_embed = discord.Embed(
                title='💬 Before you open a General Question ticket...',
                description=(
                    f'**Have you read our rules?**\n'
                    f'👉 {RULES_LINK}\n\n'
                    f'Please make sure you have read our rules before opening a ticket. '
                    f'Quick questions may already be answered in our FAQ or rules channel!'
                ),
                color=COLORS['warn']
            )
            pre_embed.add_field(name='📋 You will be asked:', value='• What is your question?\n• Any additional context?', inline=False)
            pre_embed.set_footer(text='This prompt will expire in 2 minutes.')

        await inter.response.send_message(embed=pre_embed, view=RulesCheckView(ticket_type), ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())


# ═══════════════════════════════════════════════════════════════
#  READY
# ═══════════════════════════════════════════════════════════════
@bot.event
async def on_ready():
    print(f'[READY] Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='over Sparky AI'))
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())

    # Auto-detect a channel named 'logs' and set as transcript channel if not already set
    for guild in bot.guilds:
        cfg = get_config(guild.id)
        if not cfg.get('transcriptChannelId'):
            logs_ch = discord.utils.get(guild.text_channels, name='logs')
            if logs_ch:
                set_config(guild.id, 'transcriptChannelId', str(logs_ch.id))
                print(f'[AUTO] Set transcript channel to #logs ({logs_ch.id}) in {guild.name}')

    guild_id = os.getenv('GUILD_ID')
    if guild_id:
        g = discord.Object(id=int(guild_id))
        tree.copy_global_to(guild=g)
        await tree.sync(guild=g)
        print(f'[DEPLOY] Slash commands synced to guild {guild_id}')
    else:
        await tree.sync()
        print('[DEPLOY] Global slash commands synced')
    print('[READY] Bot is fully operational.')

# ═══════════════════════════════════════════════════════════════
#  EVENTS
# ═══════════════════════════════════════════════════════════════
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    words = get_filter_words(message.guild.id)
    if words and any(w in message.content.lower() for w in words):
        await message.delete()
        m = await message.channel.send(embed=warn_embed('Message Filtered', f'{message.author.mention}, your message contained a banned word.'))
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        await m.delete()
        return
    now = time.time()
    uid = message.author.id
    spam_map.setdefault(uid, [])
    spam_map[uid] = [t for t in spam_map[uid] if now - t < 10]
    spam_map[uid].append(now)
    if len(spam_map[uid]) >= 6:
        spam_map[uid] = []
        member = message.guild.get_member(uid)
        if member and not member.guild_permissions.manage_messages:
            try:
                until = discord.utils.utcnow() + datetime.timedelta(minutes=5)
                await member.timeout(until, reason='Auto: spam detection')
                await send_log(message.guild, mod_embed('Auto Mute (Spam)', bot.user, message.author, 'Spam detection', {'Duration': '5 min'}))
                m = await message.channel.send(embed=warn_embed('Spam Detected', f'{message.author.mention} muted 5 minutes for spamming.'))
                await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=6))
                await m.delete()
            except: pass
        return
    await bot.process_commands(message)


@bot.event
async def on_member_join(member):
    cfg = get_config(member.guild.id)
    days = age_days(member)
    log_id = cfg.get('logsChannelId')
    if log_id:
        ch = member.guild.get_channel(int(log_id))
        if ch:
            e = discord.Embed(
                title=f'📥 Member Joined{"  ⚠️ NEW ACCOUNT" if days < 7 else ""}',
                color=0xFEE75C if days < 7 else 0x57F287,
                timestamp=discord.utils.utcnow()
            )
            e.set_thumbnail(url=member.display_avatar.url)
            e.add_field(name='User', value=f'{member} (`{member.id}`)', inline=True)
            e.add_field(name='Account Age', value=f'{days} days', inline=True)
            e.add_field(name='Created', value=discord.utils.format_dt(member.created_at, 'R'), inline=True)
            e.add_field(name='Members', value=str(member.guild.member_count), inline=True)
            if days < 7: e.description = '⚠️ **Account less than 7 days old!**'
            try: await ch.send(embed=e)
            except: pass
    welcome_ch = discord.utils.get(member.guild.text_channels, name='welcome')
    if not welcome_ch:
        wid = cfg.get('welcomeChannelId')
        if wid: welcome_ch = member.guild.get_channel(int(wid))
    if not welcome_ch: return
    e = discord.Embed(
        title=f'🎉 Welcome to {member.guild.name}!',
        description=(
            f'Hey {member.mention}, we\'re so glad you\'re here!\n\n'
            '> 📖 Check the rules and get started.\n'
            '> 💬 Introduce yourself to the community.\n'
            '> 🎮 Have fun and enjoy your stay!'
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name='👤 Member', value=str(member), inline=True)
    e.add_field(name='🔢 Member #', value=str(member.guild.member_count), inline=True)
    e.add_field(name='📅 Account Age', value=f'{days} days', inline=True)
    e.set_image(url=WELCOME_GIF)
    e.set_footer(text=f'You are our {member.guild.member_count}th member! 🥳', icon_url=member.guild.icon.url if member.guild.icon else None)
    try:
        await welcome_ch.send(content=f'🎊 Welcome to the server, {member.mention}! We\'ve been expecting you.', embed=e)
    except: pass


@bot.event
async def on_member_remove(member):
    cfg = get_config(member.guild.id)
    log_id = cfg.get('logsChannelId')
    if not log_id: return
    ch = member.guild.get_channel(int(log_id))
    if not ch: return
    e = discord.Embed(title='📤 Member Left', color=0xED4245, timestamp=discord.utils.utcnow())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name='User', value=f'{member} (`{member.id}`)', inline=True)
    e.add_field(name='Members', value=str(member.guild.member_count), inline=True)
    try: await ch.send(embed=e)
    except: pass

# ═══════════════════════════════════════════════════════════════
#  WARN
# ═══════════════════════════════════════════════════════════════
async def _warn(ctx_or_inter, target: discord.Member, reason='No reason provided'):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not is_mod(guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    warnings = add_warning(guild.id, target.id, mod.id, reason)
    count = len(warnings)
    add_mod_action(guild.id, target.id, {'type': 'WARN', 'moderator_id': str(mod.id), 'reason': reason})
    note = ''
    if count == 3:
        await apply_chatban(guild, target.id, 'Auto: 3 warnings', bot.user.id, 86400)
        note = '\n⚡ **Auto-escalation:** 1-day chatban applied.'
    elif count == 5:
        await apply_chatban(guild, target.id, 'Auto: 5 warnings', bot.user.id, 604800)
        note = '\n⚡ **Auto-escalation:** 1-week chatban applied.'
        try: await target.send(embed=warn_embed('Final Warning', f'5 warnings in **{guild.name}**. Next violation = temp ban.'))
        except: pass
    elif count >= 6:
        try:
            await guild.ban(target, reason='Auto: 6 warnings', delete_message_days=0)
            add_mod_action(guild.id, target.id, {'type': 'TEMPBAN', 'moderator_id': str(bot.user.id), 'reason': 'Auto: 6 warnings'})
        except: pass
        note = '\n⚡ **Auto-escalation:** 1-month temporary ban applied.'
    e = mod_embed('Warning Issued', mod, target, reason, {'Warnings': str(count)})
    if note: e.description = note
    await send_log(guild, e)
    await do_reply(ctx_or_inter, embed=e)
    try: await target.send(embed=warn_embed('You were warned', f'**Server:** {guild.name}\n**Reason:** {reason}\n**Warnings:** {count}'))
    except: pass

@bot.command(name='warn')
async def warn_cmd(ctx, target: discord.Member = None, *, reason='No reason provided'):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.warn <user> [reason]'))
    await _warn(ctx, target, reason)

@tree.command(name='warn', description='Warn a user')
@app_commands.describe(user='User to warn', reason='Reason')
async def warn_slash(inter: discord.Interaction, user: discord.Member, reason: str = 'No reason provided'):
    await inter.response.defer()
    await _warn(inter, user, reason)

# ═══════════════════════════════════════════════════════════════
#  WARNINGS
# ═══════════════════════════════════════════════════════════════
async def _warnings(ctx_or_inter, target: discord.Member):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    ws = get_warnings(ctx_or_inter.guild.id, target.id)
    if not ws: return await do_reply(ctx_or_inter, embed=info_embed('No Warnings', f'{target} has no warnings.'))
    lines = []
    for i, w in enumerate(ws):
        ts = int(datetime.datetime.fromisoformat(w['timestamp'].replace('Z', '+00:00')).timestamp())
        lines.append(f'**#{i+1}** • <t:{ts}:R>\n> {w["reason"]}\n> by <@{w["moderator_id"]}> • ID: `{w["id"]}`')
    e = discord.Embed(title=f'⚠️ Warnings for {target}', description='\n\n'.join(lines), color=COLORS['warn'])
    e.set_thumbnail(url=target.display_avatar.url)
    e.set_footer(text=f'{len(ws)} total warning(s)')
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='warnings', aliases=['infractions'])
async def warnings_cmd(ctx, target: discord.Member = None):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.warnings <user>'))
    await _warnings(ctx, target)

@tree.command(name='warnings', description='View warnings for a user')
@app_commands.describe(user='User to check')
async def warnings_slash(inter: discord.Interaction, user: discord.Member):
    await inter.response.defer()
    await _warnings(inter, user)

# ═══════════════════════════════════════════════════════════════
#  DELWARN
# ═══════════════════════════════════════════════════════════════
async def _delwarn(ctx_or_inter, target: discord.Member, warning_id: int):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    removed = remove_warning(ctx_or_inter.guild.id, target.id, warning_id)
    await do_reply(ctx_or_inter, embed=success_embed('Warning Removed', f'Removed warning `{warning_id}`.') if removed else error_embed('Not Found', 'Warning ID not found.'))

@bot.command(name='delwarn', aliases=['removewarn'])
async def delwarn_cmd(ctx, target: discord.Member = None, warning_id: int = None):
    if not target or not warning_id: return await ctx.reply(embed=error_embed('Usage', '.delwarn <user> <id>'))
    await _delwarn(ctx, target, warning_id)

@tree.command(name='delwarn', description='Delete a warning')
@app_commands.describe(user='User', warning_id='Warning ID')
async def delwarn_slash(inter: discord.Interaction, user: discord.Member, warning_id: int):
    await inter.response.defer()
    await _delwarn(inter, user, warning_id)

# ═══════════════════════════════════════════════════════════════
#  CHATBAN
# ═══════════════════════════════════════════════════════════════
async def _chatban(ctx_or_inter, target: discord.Member, reason='No reason provided'):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not is_mod(guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    await apply_chatban(guild, target.id, reason, mod.id)
    add_mod_action(guild.id, target.id, {'type': 'CHATBAN', 'moderator_id': str(mod.id), 'reason': reason})
    e = mod_embed('Chatban Applied', mod, target, reason)
    await send_log(guild, e)
    await do_reply(ctx_or_inter, embed=e)
    try: await target.send(embed=error_embed('Chatbanned', f'Chatbanned in **{guild.name}**.\n**Reason:** {reason}'))
    except: pass

@bot.command(name='chatban', aliases=['cb'])
async def chatban_cmd(ctx, target: discord.Member = None, *, reason='No reason provided'):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.chatban <user> [reason]'))
    await _chatban(ctx, target, reason)

@tree.command(name='chatban', description='Chatban a user from all channels')
@app_commands.describe(user='User to chatban', reason='Reason')
async def chatban_slash(inter: discord.Interaction, user: discord.Member, reason: str = 'No reason provided'):
    await inter.response.defer()
    await _chatban(inter, user, reason)

# ═══════════════════════════════════════════════════════════════
#  UNCHATBAN
# ═══════════════════════════════════════════════════════════════
async def _unchatban(ctx_or_inter, target: discord.Member):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not is_mod(guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    await remove_chatban(guild, target.id)
    add_mod_action(guild.id, target.id, {'type': 'UNCHATBAN', 'moderator_id': str(mod.id)})
    e = mod_embed('Chatban Removed', mod, target, 'Chatban lifted')
    await send_log(guild, e)
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='unchatban', aliases=['uncb'])
async def unchatban_cmd(ctx, target: discord.Member = None):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.unchatban <user>'))
    await _unchatban(ctx, target)

@tree.command(name='unchatban', description='Remove a chatban')
@app_commands.describe(user='User to unchatban')
async def unchatban_slash(inter: discord.Interaction, user: discord.Member):
    await inter.response.defer()
    await _unchatban(inter, user)

# ═══════════════════════════════════════════════════════════════
#  MUTE
# ═══════════════════════════════════════════════════════════════
async def _mute(ctx_or_inter, target: discord.Member, duration_str: str, reason='No reason provided'):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not is_mod(guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    secs = parse_duration(duration_str)
    if not secs: return await do_reply(ctx_or_inter, embed=error_embed('Invalid Duration', 'Use: 10m, 1h, 2d, 1w (max 28d)'))
    try:
        await target.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=secs), reason=reason)
    except Exception as ex:
        return await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))
    add_mod_action(guild.id, target.id, {'type': 'MUTE', 'moderator_id': str(mod.id), 'reason': reason, 'duration': duration_str})
    e = mod_embed('Member Muted', mod, target, reason, {'Duration': duration_str})
    await send_log(guild, e)
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='mute', aliases=['timeout'])
async def mute_cmd(ctx, target: discord.Member = None, duration: str = '10m', *, reason='No reason provided'):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.mute <user> <duration> [reason]'))
    await _mute(ctx, target, duration, reason)

@tree.command(name='mute', description='Timeout/mute a user')
@app_commands.describe(user='User to mute', duration='Duration (10m, 1h, 2d)', reason='Reason')
async def mute_slash(inter: discord.Interaction, user: discord.Member, duration: str, reason: str = 'No reason provided'):
    await inter.response.defer()
    await _mute(inter, user, duration, reason)

# ═══════════════════════════════════════════════════════════════
#  UNMUTE
# ═══════════════════════════════════════════════════════════════
async def _unmute(ctx_or_inter, target: discord.Member):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    try: await target.timeout(None, reason='Mute removed')
    except Exception as ex: return await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))
    add_mod_action(ctx_or_inter.guild.id, target.id, {'type': 'UNMUTE', 'moderator_id': str(mod.id)})
    e = mod_embed('Member Unmuted', mod, target, 'Mute removed')
    await send_log(ctx_or_inter.guild, e)
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='unmute', aliases=['untimeout'])
async def unmute_cmd(ctx, target: discord.Member = None):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.unmute <user>'))
    await _unmute(ctx, target)

@tree.command(name='unmute', description='Remove a timeout')
@app_commands.describe(user='User to unmute')
async def unmute_slash(inter: discord.Interaction, user: discord.Member):
    await inter.response.defer()
    await _unmute(inter, user)

# ═══════════════════════════════════════════════════════════════
#  KICK
# ═══════════════════════════════════════════════════════════════
async def _kick(ctx_or_inter, target: discord.Member, reason='No reason provided'):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not guild.get_member(mod.id).guild_permissions.kick_members:
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Kick Members permission.'))
    try: await target.kick(reason=reason)
    except Exception as ex: return await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))
    add_mod_action(guild.id, target.id, {'type': 'KICK', 'moderator_id': str(mod.id), 'reason': reason})
    e = mod_embed('Member Kicked', mod, target, reason)
    await send_log(guild, e)
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='kick')
async def kick_cmd(ctx, target: discord.Member = None, *, reason='No reason provided'):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.kick <user> [reason]'))
    await _kick(ctx, target, reason)

@tree.command(name='kick', description='Kick a member')
@app_commands.describe(user='User to kick', reason='Reason')
async def kick_slash(inter: discord.Interaction, user: discord.Member, reason: str = 'No reason provided'):
    await inter.response.defer()
    await _kick(inter, user, reason)

# ═══════════════════════════════════════════════════════════════
#  BAN
# ═══════════════════════════════════════════════════════════════
async def _ban(ctx_or_inter, target: discord.Member, reason='No reason provided'):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not guild.get_member(mod.id).guild_permissions.ban_members:
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Ban Members permission.'))
    try: await guild.ban(target, reason=reason, delete_message_days=7)
    except Exception as ex: return await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))
    add_mod_action(guild.id, target.id, {'type': 'BAN', 'moderator_id': str(mod.id), 'reason': reason})
    e = mod_embed('Member Banned', mod, target, reason)
    await send_log(guild, e)
    cfg = get_config(guild.id)
    owner_id = os.getenv('OWNER_ID')
    if cfg.get('logsChannelId') and owner_id:
        ch = guild.get_channel(int(cfg['logsChannelId']))
        if ch:
            try:
                ping = await ch.send(f'<@{owner_id}>')
                await ping.delete()
            except: pass
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='ban')
async def ban_cmd(ctx, target: discord.Member = None, *, reason='No reason provided'):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.ban <user> [reason]'))
    await _ban(ctx, target, reason)

@tree.command(name='ban', description='Ban a user')
@app_commands.describe(user='User to ban', reason='Reason')
async def ban_slash(inter: discord.Interaction, user: discord.Member, reason: str = 'No reason provided'):
    await inter.response.defer()
    await _ban(inter, user, reason)

# ═══════════════════════════════════════════════════════════════
#  UNBAN
# ═══════════════════════════════════════════════════════════════
async def _unban(ctx_or_inter, user_id: int, reason='No reason provided'):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not guild.get_member(mod.id).guild_permissions.ban_members:
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Ban Members permission.'))
    try:
        user = await bot.fetch_user(user_id)
        await guild.unban(user, reason=reason)
    except Exception as ex: return await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))
    add_mod_action(guild.id, user_id, {'type': 'UNBAN', 'moderator_id': str(mod.id), 'reason': reason})
    e = mod_embed('Member Unbanned', mod, user, reason)
    await send_log(guild, e)
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='unban')
async def unban_cmd(ctx, user_id: int = None, *, reason='No reason provided'):
    if not user_id: return await ctx.reply(embed=error_embed('Usage', '.unban <user_id> [reason]'))
    await _unban(ctx, user_id, reason)

@tree.command(name='unban', description='Unban a user by ID')
@app_commands.describe(user_id='User ID to unban', reason='Reason')
async def unban_slash(inter: discord.Interaction, user_id: str, reason: str = 'No reason provided'):
    await inter.response.defer()
    try: await _unban(inter, int(user_id), reason)
    except: await do_reply(inter, embed=error_embed('Invalid ID', 'Provide a valid user ID.'))

# ═══════════════════════════════════════════════════════════════
#  USERCHECK
# ═══════════════════════════════════════════════════════════════
async def _usercheck(ctx_or_inter, target: discord.Member):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not is_mod(guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    ws = get_warnings(guild.id, target.id)
    acts = get_mod_actions(guild.id, target.id)
    days = age_days(target)
    e = discord.Embed(title=f'🔍 User Check: {target}', color=COLORS['info'], timestamp=discord.utils.utcnow())
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name='👤 User', value=f'{target.mention} (`{target.id}`)', inline=True)
    e.add_field(name='📅 Created', value=discord.utils.format_dt(target.created_at, 'R'), inline=True)
    e.add_field(name='📆 Age', value=f'{days} days {"⚠️" if days < 7 else ""}', inline=True)
    e.add_field(name='📥 Joined', value=discord.utils.format_dt(target.joined_at, 'R') if target.joined_at else 'Unknown', inline=True)
    roles = [r.mention for r in target.roles if r.name != '@everyone']
    e.add_field(name='🏷️ Roles', value=' '.join(roles) if roles else 'None', inline=False)
    warn_lines = '\n'.join([f'• {w["reason"]}' for w in ws[-3:]]) or 'None'
    e.add_field(name=f'⚠️ Warnings ({len(ws)})', value=warn_lines, inline=False)
    act_lines = '\n'.join([f'• **{a["type"]}** — {a.get("reason", "")[:40]}' for a in acts[-5:]]) or 'None'
    e.add_field(name=f'🔨 Actions ({len(acts)})', value=act_lines, inline=False)
    alts = [m for m in guild.members if m.id != target.id and abs((m.created_at - target.created_at).total_seconds()) < 86400]
    if alts: e.add_field(name='🔁 Possible Alts', value='\n'.join(str(a) for a in alts[:10]), inline=False)
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='usercheck', aliases=['uc', 'check'])
async def usercheck_cmd(ctx, target: discord.Member = None):
    await _usercheck(ctx, target or ctx.author)

@tree.command(name='usercheck', description='View user info and mod history')
@app_commands.describe(user='User to check')
async def usercheck_slash(inter: discord.Interaction, user: discord.Member):
    await inter.response.defer()
    await _usercheck(inter, user)

# ═══════════════════════════════════════════════════════════════
#  NOTE / NOTES / DELNOTE
# ═══════════════════════════════════════════════════════════════
async def _note(ctx_or_inter, target: discord.Member, text: str):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    entry = add_note(ctx_or_inter.guild.id, target.id, mod.id, text)
    await do_reply(ctx_or_inter, embed=success_embed('Note Added', f'Added note for {target}.\n> {text}\nID: `{entry["id"]}`'))

async def _notes(ctx_or_inter, target: discord.Member):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    notes = get_notes(ctx_or_inter.guild.id, target.id)
    if not notes: return await do_reply(ctx_or_inter, embed=info_embed('No Notes', f'No notes for {target}.'))
    lines = [f'**#{i+1}** by <@{n["moderator_id"]}>\n> {n["note"]}\n> ID: `{n["id"]}`' for i, n in enumerate(notes)]
    e = discord.Embed(title=f'📝 Notes for {target}', description='\n\n'.join(lines), color=COLORS['info'])
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='note')
async def note_cmd(ctx, target: discord.Member = None, *, text=None):
    if not target or not text: return await ctx.reply(embed=error_embed('Usage', '.note <user> <text>'))
    await _note(ctx, target, text)

@tree.command(name='note', description='Add a private mod note')
@app_commands.describe(user='User', text='Note text')
async def note_slash(inter: discord.Interaction, user: discord.Member, text: str):
    await inter.response.defer()
    await _note(inter, user, text)

@bot.command(name='notes')
async def notes_cmd(ctx, target: discord.Member = None):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.notes <user>'))
    await _notes(ctx, target)

@tree.command(name='notes', description='View notes for a user')
@app_commands.describe(user='User')
async def notes_slash(inter: discord.Interaction, user: discord.Member):
    await inter.response.defer()
    await _notes(inter, user)

@bot.command(name='delnote')
async def delnote_cmd(ctx, target: discord.Member = None, note_id: int = None):
    if not is_mod(ctx.author): return await ctx.reply(embed=error_embed('No Permission', 'You need moderation permissions.'))
    if not target or not note_id: return await ctx.reply(embed=error_embed('Usage', '.delnote <user> <id>'))
    removed = remove_note(ctx.guild.id, target.id, note_id)
    await ctx.reply(embed=success_embed('Note Deleted', 'Removed.') if removed else error_embed('Not Found', 'Note ID not found.'))

@tree.command(name='delnote', description='Delete a note')
@app_commands.describe(user='User', note_id='Note ID')
async def delnote_slash(inter: discord.Interaction, user: discord.Member, note_id: int):
    await inter.response.defer()
    if not is_mod(inter.guild.get_member(inter.user.id)):
        return await do_reply(inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    removed = remove_note(inter.guild.id, user.id, note_id)
    await do_reply(inter, embed=success_embed('Note Deleted', 'Removed.') if removed else error_embed('Not Found', 'Note ID not found.'))

# ═══════════════════════════════════════════════════════════════
#  LOCK / UNLOCK
# ═══════════════════════════════════════════════════════════════
async def _lock(ctx_or_inter):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    ch = ctx_or_inter.channel
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    try:
        await ch.set_permissions(ctx_or_inter.guild.default_role, send_messages=False)
        await do_reply(ctx_or_inter, embed=success_embed('Channel Locked', f'{ch.mention} is now locked.'))
        await send_log(ctx_or_inter.guild, mod_embed('Channel Locked', mod, ch, 'Manual lock'))
    except Exception as ex:
        await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))

async def _unlock(ctx_or_inter):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    ch = ctx_or_inter.channel
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    try:
        await ch.set_permissions(ctx_or_inter.guild.default_role, send_messages=None)
        await do_reply(ctx_or_inter, embed=success_embed('Channel Unlocked', f'{ch.mention} is now unlocked.'))
        await send_log(ctx_or_inter.guild, mod_embed('Channel Unlocked', mod, ch, 'Manual unlock'))
    except Exception as ex:
        await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))

@bot.command(name='lock')
async def lock_cmd(ctx): await _lock(ctx)

@bot.command(name='unlock')
async def unlock_cmd(ctx): await _unlock(ctx)

@tree.command(name='lock', description='Lock the current channel')
async def lock_slash(inter: discord.Interaction):
    await inter.response.defer()
    await _lock(inter)

@tree.command(name='unlock', description='Unlock the current channel')
async def unlock_slash(inter: discord.Interaction):
    await inter.response.defer()
    await _unlock(inter)

# ═══════════════════════════════════════════════════════════════
#  LOCKDOWN / UNLOCKALL
# ═══════════════════════════════════════════════════════════════
async def _lockdown(ctx_or_inter):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not is_admin(guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    count = 0
    for ch in guild.text_channels:
        try:
            await ch.set_permissions(guild.default_role, send_messages=False)
            count += 1
        except: pass
    await send_log(guild, mod_embed('🔒 SERVER LOCKDOWN', mod, guild, f'Locked {count} channels'))
    await do_reply(ctx_or_inter, embed=warn_embed('Lockdown Active', f'Locked **{count}** channels.'))

async def _unlockall(ctx_or_inter):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    guild = ctx_or_inter.guild
    if not is_admin(guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    count = 0
    for ch in guild.text_channels:
        try:
            await ch.set_permissions(guild.default_role, send_messages=None)
            count += 1
        except: pass
    await do_reply(ctx_or_inter, embed=success_embed('Lockdown Lifted', f'Unlocked **{count}** channels.'))

@bot.command(name='lockdown')
async def lockdown_cmd(ctx): await _lockdown(ctx)

@bot.command(name='unlockall')
async def unlockall_cmd(ctx): await _unlockall(ctx)

@tree.command(name='lockdown', description='Lock all channels')
async def lockdown_slash(inter: discord.Interaction):
    await inter.response.defer()
    await _lockdown(inter)

@tree.command(name='unlockall', description='Unlock all channels')
async def unlockall_slash(inter: discord.Interaction):
    await inter.response.defer()
    await _unlockall(inter)

# ═══════════════════════════════════════════════════════════════
#  NUKE
# ═══════════════════════════════════════════════════════════════
async def _nuke(ctx_or_inter):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    ch = ctx_or_inter.channel
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    try:
        new_ch = await ch.clone(reason=f'Nuked by {mod}')
        await new_ch.edit(position=ch.position)
        await ch.delete(reason=f'Nuked by {mod}')
        await new_ch.send(embed=success_embed('Channel Nuked', '💣 Channel has been nuked and recreated. RIP to every message that didn\'t make it out alive. Thoughts and prayers. 🕯️').set_image(url='https://media1.tenor.com/m/qufV4aucOi8AAAAC/pocoyo-dance.gif'))
        await send_log(ctx_or_inter.guild, mod_embed('Channel Nuked', mod, ch, 'Nuke command'))
    except Exception as ex:
        await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))

@bot.command(name='nuke')
async def nuke_cmd(ctx): await _nuke(ctx)

@tree.command(name='nuke', description='Clone and delete current channel')
async def nuke_slash(inter: discord.Interaction):
    await inter.response.defer()
    await _nuke(inter)

# ═══════════════════════════════════════════════════════════════
#  NICKNAME
# ═══════════════════════════════════════════════════════════════
async def _nickname(ctx_or_inter, target: discord.Member, new_nick=None):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    try:
        await target.edit(nick=new_nick)
        await do_reply(ctx_or_inter, embed=success_embed('Nickname Changed', f'{target.mention} nickname set to: **{new_nick or "(reset)"}**'))
    except Exception as ex:
        await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))

@bot.command(name='nickname', aliases=['nick'])
async def nickname_cmd(ctx, target: discord.Member = None, *, new_nick=None):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.nickname <user> [new name]'))
    await _nickname(ctx, target, new_nick)

@tree.command(name='nickname', description="Force change a user's nickname")
@app_commands.describe(user='User', nickname='New nickname (leave blank to reset)')
async def nickname_slash(inter: discord.Interaction, user: discord.Member, nickname: str = None):
    await inter.response.defer()
    await _nickname(inter, user, nickname)

# ═══════════════════════════════════════════════════════════════
#  ROLE
# ═══════════════════════════════════════════════════════════════
async def _role(ctx_or_inter, target: discord.Member, role: discord.Role):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    try:
        if role in target.roles:
            await target.remove_roles(role)
            await do_reply(ctx_or_inter, embed=success_embed('Role Removed', f'Removed {role.mention} from {target.mention}.'))
        else:
            await target.add_roles(role)
            await do_reply(ctx_or_inter, embed=success_embed('Role Added', f'Added {role.mention} to {target.mention}.'))
    except Exception as ex:
        await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))

@bot.command(name='role')
async def role_cmd(ctx, target: discord.Member = None, role: discord.Role = None):
    if not target or not role: return await ctx.reply(embed=error_embed('Usage', '.role <user> <role>'))
    await _role(ctx, target, role)

@tree.command(name='role', description='Add or remove a role from a user')
@app_commands.describe(user='User', role='Role to add/remove')
async def role_slash(inter: discord.Interaction, user: discord.Member, role: discord.Role):
    await inter.response.defer()
    await _role(inter, user, role)

# ═══════════════════════════════════════════════════════════════
#  PURGE
# ═══════════════════════════════════════════════════════════════
async def _purge(ctx_or_inter, amount: int):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not ctx_or_inter.guild.get_member(mod.id).guild_permissions.manage_messages:
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Messages permission.'))
    if not 1 <= amount <= 100:
        return await do_reply(ctx_or_inter, embed=error_embed('Invalid', 'Amount must be 1–100.'))
    try:
        ch = ctx_or_inter.channel
        deleted = await ch.purge(limit=amount)
        m = await ch.send(embed=success_embed('Purge Complete', f'Deleted **{len(deleted)}** messages.'))
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=4))
        await m.delete()
    except Exception as ex:
        await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))

@bot.command(name='purge', aliases=['clear', 'prune'])
async def purge_cmd(ctx, amount: int = None):
    if not amount: return await ctx.reply(embed=error_embed('Usage', '.purge <1-100>'))
    await _purge(ctx, amount)

@tree.command(name='purge', description='Bulk delete messages')
@app_commands.describe(amount='Number of messages to delete (1-100)')
async def purge_slash(inter: discord.Interaction, amount: int):
    await inter.response.defer(ephemeral=True)
    await _purge(inter, amount)

# ═══════════════════════════════════════════════════════════════
#  SLOWMODE
# ═══════════════════════════════════════════════════════════════
async def _slowmode(ctx_or_inter, seconds: int):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    if not 0 <= seconds <= 21600:
        return await do_reply(ctx_or_inter, embed=error_embed('Invalid', 'Slowmode must be 0–21600 seconds.'))
    try:
        await ctx_or_inter.channel.edit(slowmode_delay=seconds)
        msg = 'Slowmode disabled.' if seconds == 0 else f'Slowmode set to **{seconds}s**.'
        await do_reply(ctx_or_inter, embed=success_embed('Slowmode Set', msg))
    except Exception as ex:
        await do_reply(ctx_or_inter, embed=error_embed('Failed', str(ex)))

@bot.command(name='slowmode', aliases=['slow'])
async def slowmode_cmd(ctx, seconds: int = None):
    if seconds is None: return await ctx.reply(embed=error_embed('Usage', '.slowmode <0-21600>'))
    await _slowmode(ctx, seconds)

@tree.command(name='slowmode', description='Set channel slowmode')
@app_commands.describe(seconds='Slowmode in seconds (0 to disable)')
async def slowmode_slash(inter: discord.Interaction, seconds: int):
    await inter.response.defer()
    await _slowmode(inter, seconds)

# ═══════════════════════════════════════════════════════════════
#  FILTER
# ═══════════════════════════════════════════════════════════════
@bot.command(name='filter')
async def filter_cmd(ctx, sub: str = None, *, word: str = None):
    if not is_mod(ctx.author): return await ctx.reply(embed=error_embed('No Permission', 'You need moderation permissions.'))
    if sub == 'add':
        if not word: return await ctx.reply(embed=error_embed('Usage', '.filter add <word>'))
        added = add_filter_word(ctx.guild.id, word)
        await ctx.reply(embed=success_embed('Word Added', f'`{word}` added.') if added else info_embed('Already Filtered', f'`{word}` is already filtered.'))
    elif sub in ('remove', 'del'):
        if not word: return await ctx.reply(embed=error_embed('Usage', '.filter remove <word>'))
        removed = remove_filter_word(ctx.guild.id, word)
        await ctx.reply(embed=success_embed('Word Removed', f'`{word}` removed.') if removed else error_embed('Not Found', f'`{word}` not in filter.'))
    elif sub == 'list' or sub is None:
        words = get_filter_words(ctx.guild.id)
        await ctx.reply(embed=info_embed('Filter List', f'`{"`, `".join(words)}`' if words else 'No filtered words.'))
    else:
        await ctx.reply(embed=error_embed('Usage', '.filter add/remove/list [word]'))

@tree.command(name='filter_add', description='Add a word to the filter')
@app_commands.describe(word='Word to filter')
async def filter_add_slash(inter: discord.Interaction, word: str):
    await inter.response.defer()
    if not is_mod(inter.guild.get_member(inter.user.id)):
        return await do_reply(inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    added = add_filter_word(inter.guild.id, word)
    await do_reply(inter, embed=success_embed('Word Added', f'`{word}` added.') if added else info_embed('Already Filtered', f'`{word}` already filtered.'))

@tree.command(name='filter_remove', description='Remove a word from the filter')
@app_commands.describe(word='Word to remove')
async def filter_remove_slash(inter: discord.Interaction, word: str):
    await inter.response.defer()
    if not is_mod(inter.guild.get_member(inter.user.id)):
        return await do_reply(inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    removed = remove_filter_word(inter.guild.id, word)
    await do_reply(inter, embed=success_embed('Word Removed', f'`{word}` removed.') if removed else error_embed('Not Found', f'`{word}` not in filter.'))

@tree.command(name='filter_list', description='List all filtered words')
async def filter_list_slash(inter: discord.Interaction):
    await inter.response.defer()
    if not is_mod(inter.guild.get_member(inter.user.id)):
        return await do_reply(inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    words = get_filter_words(inter.guild.id)
    await do_reply(inter, embed=info_embed('Filter List', f'`{"`, `".join(words)}`' if words else 'No filtered words.'))

# ═══════════════════════════════════════════════════════════════
#  AVATAR
# ═══════════════════════════════════════════════════════════════
async def _avatar(ctx_or_inter, target=None):
    user = target or (ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user)
    e = discord.Embed(title=f'🖼️ {user}\'s Avatar', color=COLORS['info'])
    e.set_image(url=user.display_avatar.url)
    e.description = (f'[PNG]({user.display_avatar.replace(format="png", size=1024).url}) | '
                     f'[WebP]({user.display_avatar.replace(format="webp", size=1024).url}) | '
                     f'[JPG]({user.display_avatar.replace(format="jpg", size=1024).url})')
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='avatar', aliases=['av', 'pfp'])
async def avatar_cmd(ctx, target: discord.Member = None):
    await _avatar(ctx, target)

@tree.command(name='avatar', description="Show a user's avatar")
@app_commands.describe(user='User (defaults to yourself)')
async def avatar_slash(inter: discord.Interaction, user: discord.Member = None):
    await inter.response.defer()
    await _avatar(inter, user)

# ═══════════════════════════════════════════════════════════════
#  SERVERINFO
# ═══════════════════════════════════════════════════════════════
async def _serverinfo(ctx_or_inter):
    guild = ctx_or_inter.guild
    e = discord.Embed(title=f'📊 {guild.name}', color=COLORS['info'], timestamp=discord.utils.utcnow())
    if guild.icon: e.set_thumbnail(url=guild.icon.url)
    if guild.banner: e.set_image(url=guild.banner.url)
    e.add_field(name='👑 Owner', value=f'<@{guild.owner_id}>', inline=True)
    e.add_field(name='📅 Created', value=discord.utils.format_dt(guild.created_at, 'R'), inline=True)
    e.add_field(name='👥 Members', value=str(guild.member_count), inline=True)
    e.add_field(name='💬 Channels', value=str(len(guild.channels)), inline=True)
    e.add_field(name='🎭 Roles', value=str(len(guild.roles)), inline=True)
    e.add_field(name='🆔 Server ID', value=str(guild.id), inline=True)
    if guild.description: e.description = guild.description
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='serverinfo', aliases=['si', 'server'])
async def serverinfo_cmd(ctx): await _serverinfo(ctx)

@tree.command(name='serverinfo', description='Show server information')
async def serverinfo_slash(inter: discord.Interaction):
    await inter.response.defer()
    await _serverinfo(inter)

# ═══════════════════════════════════════════════════════════════
#  LOGSCHANNEL
# ═══════════════════════════════════════════════════════════════
async def _logschannel(ctx_or_inter, channel: discord.TextChannel):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    set_config(ctx_or_inter.guild.id, 'logsChannelId', str(channel.id))
    await do_reply(ctx_or_inter, embed=success_embed('Logs Channel Set', f'Mod logs will be sent to {channel.mention}.'))

@bot.command(name='logschannel', aliases=['setlogs', 'logs'])
async def logschannel_cmd(ctx, channel: discord.TextChannel = None):
    if not channel: return await ctx.reply(embed=error_embed('Usage', '.logschannel #channel'))
    await _logschannel(ctx, channel)

@tree.command(name='logschannel', description='Set the mod logs channel')
@app_commands.describe(channel='Channel for mod logs')
async def logschannel_slash(inter: discord.Interaction, channel: discord.TextChannel):
    await inter.response.defer()
    await _logschannel(inter, channel)

# ═══════════════════════════════════════════════════════════════
#  WELCOMECHANNEL
# ═══════════════════════════════════════════════════════════════
async def _welcomechannel(ctx_or_inter, channel: discord.TextChannel):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    set_config(ctx_or_inter.guild.id, 'welcomeChannelId', str(channel.id))
    await do_reply(ctx_or_inter, embed=success_embed('Welcome Channel Set', f'Welcome messages will be sent to {channel.mention}.\n\nThe bot also auto-detects any channel named `welcome`.'))

@bot.command(name='welcomechannel', aliases=['setwelcome'])
async def welcomechannel_cmd(ctx, channel: discord.TextChannel = None):
    if not channel: return await ctx.reply(embed=error_embed('Usage', '.welcomechannel #channel'))
    await _welcomechannel(ctx, channel)

@tree.command(name='welcomechannel', description='Set the welcome messages channel')
@app_commands.describe(channel='Channel for welcome messages')
async def welcomechannel_slash(inter: discord.Interaction, channel: discord.TextChannel):
    await inter.response.defer()
    await _welcomechannel(inter, channel)

# ═══════════════════════════════════════════════════════════════
#  TRANSCRIPT CHANNEL
# ═══════════════════════════════════════════════════════════════
async def _transcriptchannel(ctx_or_inter, channel: discord.TextChannel):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    set_config(ctx_or_inter.guild.id, 'transcriptChannelId', str(channel.id))
    await do_reply(ctx_or_inter, embed=success_embed(
        'Transcript Channel Set',
        f'Ticket transcripts will be saved to {channel.mention}.\n\n'
        f'The bot also auto-detects a channel named `logs` if none is set.'
    ))

@bot.command(name='transcriptchannel', aliases=['settranscripts', 'transcripts'])
async def transcriptchannel_cmd(ctx, channel: discord.TextChannel = None):
    if not channel: return await ctx.reply(embed=error_embed('Usage', '.transcriptchannel #channel'))
    await _transcriptchannel(ctx, channel)

@tree.command(name='transcriptchannel', description='Set the channel where ticket transcripts are saved')
@app_commands.describe(channel='Channel for ticket transcripts')
async def transcriptchannel_slash(inter: discord.Interaction, channel: discord.TextChannel):
    await inter.response.defer()
    await _transcriptchannel(inter, channel)

# ═══════════════════════════════════════════════════════════════
#  REVIEW PANEL
# ═══════════════════════════════════════════════════════════════
async def _reviewpanel(ctx_or_inter, target: discord.Member):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_mod(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need moderation permissions.'))
    cb = get_chatban(ctx_or_inter.guild.id, target.id)
    ws = get_warnings(ctx_or_inter.guild.id, target.id)
    e = discord.Embed(title='🔍 Chatban Review Panel', color=COLORS['mod'], timestamp=discord.utils.utcnow())
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name='User', value=f'{target} (`{target.id}`)')
    e.add_field(name='Status', value='🔴 Chatbanned' if cb else '🟢 Not Chatbanned', inline=True)
    e.add_field(name='Warnings', value=str(len(ws)), inline=True)
    e.add_field(name='Reason', value=cb['reason'] if cb else 'N/A', inline=False)
    e.add_field(name='Applied', value=cb['applied_at'] if cb else 'N/A', inline=True)
    e.add_field(name='Expires', value=cb.get('expires_at', 'Permanent') if cb else 'N/A', inline=True)

    view = discord.ui.View(timeout=300)

    async def make_button(label, style, action):
        btn = discord.ui.Button(label=label, style=style)
        async def callback(interaction: discord.Interaction):
            if not is_mod(interaction.guild.get_member(interaction.user.id)):
                return await interaction.response.send_message(embed=error_embed('No Permission', 'Staff only.'), ephemeral=True)
            await interaction.response.defer()
            if action == 'remove':
                await remove_chatban(interaction.guild, target.id)
                add_mod_action(interaction.guild.id, target.id, {'type': 'UNCHATBAN', 'moderator_id': str(interaction.user.id), 'reason': 'Review panel'})
                await interaction.followup.send(embed=success_embed('Chatban Removed', f'{target}\'s chatban lifted.'))
                await send_log(interaction.guild, mod_embed('Chatban Removed (Panel)', interaction.user, target, 'Review panel'))
            elif action == 'increase':
                existing = get_chatban(interaction.guild.id, target.id)
                if existing:
                    existing['expires_at'] = None
                    set_chatban(interaction.guild.id, target.id, existing)
                else:
                    await apply_chatban(interaction.guild, target.id, 'Review panel: increased', interaction.user.id)
                await interaction.followup.send(embed=warn_embed('Ban Increased', f'{target}\'s chatban is now permanent.'))
            elif action == 'decrease':
                existing = get_chatban(interaction.guild.id, target.id)
                if existing:
                    existing['expires_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 86400))
                    set_chatban(interaction.guild.id, target.id, existing)
                await interaction.followup.send(embed=success_embed('Ban Decreased', f'{target}\'s chatban reduced to 1 day.'))
            elif action == 'keep':
                await interaction.followup.send(embed=info_embed('No Change', f'{target}\'s chatban kept as-is.'), ephemeral=True)
        btn.callback = callback
        view.add_item(btn)

    await make_button('⬆ Increase Ban', discord.ButtonStyle.danger, 'increase')
    await make_button('⬇ Decrease Ban', discord.ButtonStyle.primary, 'decrease')
    await make_button('🔓 Remove Ban', discord.ButtonStyle.success, 'remove')
    await make_button('✅ Keep As-Is', discord.ButtonStyle.secondary, 'keep')
    await do_reply(ctx_or_inter, embed=e, view=view)

@bot.command(name='reviewpanel', aliases=['cbpanel', 'cbr'])
async def reviewpanel_cmd(ctx, target: discord.Member = None):
    if not target: return await ctx.reply(embed=error_embed('Usage', '.reviewpanel <user>'))
    await _reviewpanel(ctx, target)

@tree.command(name='reviewpanel', description='Open chatban review panel')
@app_commands.describe(user='User to review')
async def reviewpanel_slash(inter: discord.Interaction, user: discord.Member):
    await inter.response.defer()
    await _reviewpanel(inter, user)

# ═══════════════════════════════════════════════════════════════
#  TICKET PANEL COMMAND
# ═══════════════════════════════════════════════════════════════
async def _ticketpanel(ctx_or_inter, channel: discord.TextChannel = None):
    mod = ctx_or_inter.author if isinstance(ctx_or_inter, commands.Context) else ctx_or_inter.user
    if not is_admin(ctx_or_inter.guild.get_member(mod.id)):
        return await do_reply(ctx_or_inter, embed=error_embed('No Permission', 'You need Manage Guild permission.'))
    target_ch = channel or ctx_or_inter.channel
    e = discord.Embed(
        title='🎫 Sparky AI Support',
        description=(
            'Need help? Want to buy Sparky AI? Have a question?\n\n'
            '**Select a category below to open a ticket.**\n\n'
            '🛠️ **Support** — Technical issues and troubleshooting\n'
            '💳 **Buy Sparky AI** — Purchase enquiries and plans\n'
            '💬 **General Question** — Anything else\n\n'
            '*A staff member will assist you as soon as possible.*'
        ),
        color=0x5865F2
    )
    e.set_footer(text='Sparky AI • Support System')
    if ctx_or_inter.guild.icon:
        e.set_thumbnail(url=ctx_or_inter.guild.icon.url)
    await target_ch.send(embed=e, view=TicketPanelView())
    if target_ch != ctx_or_inter.channel:
        await do_reply(ctx_or_inter, embed=success_embed('Panel Sent', f'Ticket panel posted in {target_ch.mention}.'))

@bot.command(name='ticketpanel', aliases=['tp', 'tickets'])
async def ticketpanel_cmd(ctx, channel: discord.TextChannel = None):
    await _ticketpanel(ctx, channel)

@tree.command(name='ticketpanel', description='Post the ticket panel in a channel')
@app_commands.describe(channel='Channel to post the panel in (defaults to current)')
async def ticketpanel_slash(inter: discord.Interaction, channel: discord.TextChannel = None):
    await inter.response.defer()
    await _ticketpanel(inter, channel)

# ═══════════════════════════════════════════════════════════════
#  HELP
# ═══════════════════════════════════════════════════════════════
async def _help(ctx_or_inter):
    e = discord.Embed(title='📚 Moderation Bot Commands', description='Prefix: `.` or `?` — All commands also work as `/command`', color=COLORS['info'])
    e.add_field(name='⚠️ Warnings',      value='`warn` `warnings` `delwarn`',                                   inline=True)
    e.add_field(name='🔇 Restrictions',  value='`chatban` `unchatban` `mute` `unmute`',                         inline=True)
    e.add_field(name='🔨 Moderation',    value='`kick` `ban` `unban`',                                          inline=True)
    e.add_field(name='🔍 Info',          value='`usercheck` `avatar` `serverinfo`',                             inline=True)
    e.add_field(name='📝 Notes',         value='`note` `notes` `delnote`',                                      inline=True)
    e.add_field(name='📢 Channels',      value='`lock` `unlock` `lockdown` `unlockall` `nuke`',                 inline=True)
    e.add_field(name='🛠️ User Mgmt',    value='`nickname` `role` `slowmode` `purge`',                          inline=True)
    e.add_field(name='🚫 Filter',        value='`filter add/remove/list`',                                      inline=True)
    e.add_field(name='🎫 Tickets',       value='`ticketpanel [#channel]`',                                      inline=True)
    e.add_field(name='⚙️ Config',        value='`logschannel` `welcomechannel` `transcriptchannel` `reviewpanel`', inline=True)
    e.set_footer(text='Duration format: 10s, 10m, 1h, 2d, 1w  |  Transcripts auto-save to #logs if set')
    await do_reply(ctx_or_inter, embed=e)

@bot.command(name='help', aliases=['h', 'commands'])
async def help_cmd(ctx): await _help(ctx)

@tree.command(name='help', description='Show all commands')
async def help_slash(inter: discord.Interaction):
    await inter.response.defer()
    await _help(inter)

# ═══════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════
if not os.getenv('DISCORD_TOKEN'):
    print('[ERROR] DISCORD_TOKEN not set. Check your .env file.')
    exit(1)

bot.run(os.getenv('DISCORD_TOKEN'))
