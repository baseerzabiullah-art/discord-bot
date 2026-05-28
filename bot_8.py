================================================================================
FILE: discord-bot/.env.example
================================================================================

# Discord Bot Token (from Discord Developer Portal)
DISCORD_TOKEN=your_bot_token_here

# Your Discord Server ID
GUILD_ID=your_guild_id_here

# Your Discord User ID (bot owner)
OWNER_ID=your_user_id_here



================================================================================
FILE: discord-bot/.gitignore
================================================================================

node_modules/
.env
data/
*.log



================================================================================
FILE: discord-bot/README.md
================================================================================

# Sparky AI Moderation Bot

A production-ready Discord moderation bot with prefix commands (`.` / `?`) and slash commands.

---

## 🚀 Setup

### 1. Prerequisites
- Node.js 18+ installed
- A Discord bot application from the [Developer Portal](https://discord.com/developers/applications)

### 2. Bot Permissions
When inviting your bot, ensure it has these permissions:
- **Administrator** (recommended for full functionality)

OR individually:
- Manage Channels, Manage Roles, Manage Nicknames
- Kick Members, Ban Members
- Moderate Members (for timeouts)
- Manage Messages
- Read/Send Messages, View Channels

Enable these **Privileged Gateway Intents** in the Developer Portal:
- ✅ Server Members Intent
- ✅ Message Content Intent

### 3. Installation
```bash
git clone <your-repo>
cd discord-bot
npm install
cp .env.example .env
```

Edit `.env`:
```
DISCORD_TOKEN=your_bot_token_here
GUILD_ID=your_server_id_here        # For instant slash command registration
OWNER_ID=your_discord_user_id_here  # For ghost pings on bans
```

### 4. Run
```bash
npm start
```

---

## 🚂 Railway Deployment

1. Push this project to a GitHub repository
2. Create a new project on [Railway](https://railway.app)
3. Connect your GitHub repository
4. Add environment variables in Railway's dashboard:
   - `DISCORD_TOKEN`
   - `GUILD_ID`
   - `OWNER_ID`
5. Deploy — Railway will auto-start with `node index.js`

The bot will run 24/7. Railway's free tier offers 500 hours/month.

---

## 📋 Commands

All commands work with `.command`, `?command`, and `/command`.

### Warnings
| Command | Description |
|---|---|
| `warn <user> [reason]` | Warn a user (auto-escalates at 3/5/6 warnings) |
| `warnings <user>` | View all warnings for a user |
| `delwarn <user> <id>` | Delete a specific warning |

**Auto-escalation:**
- 3 warnings → 1-day chatban
- 5 warnings → 1-week chatban + final warning DM
- 6+ warnings → 1-month temporary ban

### Chat Restrictions
| Command | Description |
|---|---|
| `chatban <user> [reason]` | Block all chat access across every channel |
| `unchatban <user>` | Remove a chatban |
| `mute <user> <duration> [reason]` | Discord timeout (e.g. `10m`, `1h`, `2d`, `1w`) |
| `unmute <user>` | Remove a timeout |

### Moderation
| Command | Description |
|---|---|
| `kick <user> [reason]` | Kick a member |
| `ban <user> [reason]` | Ban a user |
| `unban <id> [reason]` | Unban a user by ID |

### User Info
| Command | Description |
|---|---|
| `usercheck <user>` | Full mod profile: join date, warnings, actions, possible alts |
| `avatar [user]` | Show user's avatar |
| `serverinfo` | Server statistics |
| `note <user> <text>` | Add a private mod note |
| `notes <user>` | View all notes for a user |
| `delnote <user> <id>` | Delete a note |

### Channel Management
| Command | Description |
|---|---|
| `lock` | Lock current channel |
| `unlock` | Unlock current channel |
| `lockdown` | Lock ALL channels |
| `unlockall` | Unlock ALL channels |
| `nuke` | Clone & delete channel (wipes all messages) |
| `slowmode <seconds>` | Set slowmode (0 to disable) |
| `purge <amount>` | Delete 1–100 messages |

### User Management
| Command | Description |
|---|---|
| `nickname <user> [name]` | Force change nickname (omit name to reset) |
| `role <user> <role>` | Toggle a role on a user |

### Filter
| Command | Description |
|---|---|
| `filter add <word>` | Add word to automod filter |
| `filter remove <word>` | Remove word from filter |
| `filter list` | List all filtered words |

### Config & Logging
| Command | Description |
|---|---|
| `logschannel <#channel>` | Set the mod logs channel |
| `reviewpanel <user>` | Open chatban review panel with action buttons |
| `help` | Show all commands |

---

## 🤖 Auto Features

- **Spam Detection:** 6+ messages in 10 seconds → 5-minute automatic timeout
- **Word Filter:** Auto-deletes messages containing banned words
- **Join Logs:** Logs new members with account age warning if < 7 days old
- **Leave Logs:** Logs members who leave
- **Ban Logs:** Ghost pings server owner on manual bans
- **Status:** `Watching over Sparky AI`

---

## 📁 File Structure

```
discord-bot/
├── index.js                  # Entry point
├── package.json
├── railway.toml              # Railway deployment config
├── .env.example
├── commands/
│   └── moderation.js         # All command handlers
├── events/
│   └── handlers.js           # Event listeners
├── utils/
│   ├── database.js           # JSON-based data storage
│   ├── helpers.js            # Embeds, permissions, utilities
│   ├── chatban.js            # Chatban apply/remove logic
│   └── registerCommands.js   # Slash command registration
└── data/                     # Auto-created, stores JSON data
    ├── warnings.json
    ├── modactions.json
    ├── notes.json
    ├── config.json
    ├── filter.json
    └── chatbans.json
```

---

## ⚠️ Notes

- Data is stored in JSON files in the `/data` directory. For production at scale, consider migrating to SQLite or a database.
- On Railway, the `/data` directory persists between deployments as long as you don't change the volume. Consider using Railway Volumes for persistent storage.
- The bot registers slash commands to your `GUILD_ID` for instant availability. Remove `GUILD_ID` to register globally (takes up to 1 hour to propagate).



================================================================================
FILE: discord-bot/index.js
================================================================================

require('dotenv').config();
const { Client, GatewayIntentBits, Partials, ActivityType } = require('discord.js');
const { handleMessage, handleInteraction, handleMemberAdd, handleMemberRemove } = require('./events/handlers');
const { registerCommands } = require('./utils/registerCommands');

// ── Validate environment ────────────────────────────────────────
if (!process.env.DISCORD_TOKEN) {
  console.error('[ERROR] DISCORD_TOKEN is not set. Please check your .env file.');
  process.exit(1);
}

// ── Create client ───────────────────────────────────────────────
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildModeration,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages
  ],
  partials: [Partials.Message, Partials.Channel, Partials.GuildMember]
});

// ── Ready ───────────────────────────────────────────────────────
client.once('ready', async () => {
  console.log(`[READY] Logged in as ${client.user.tag}`);

  client.user.setPresence({
    activities: [{ name: 'over Sparky AI', type: ActivityType.Watching }],
    status: 'online'
  });

  await registerCommands();
  console.log('[READY] Bot is fully operational.');
});

// ── Events ──────────────────────────────────────────────────────
client.on('messageCreate', handleMessage);
client.on('interactionCreate', handleInteraction);
client.on('guildMemberAdd', handleMemberAdd);
client.on('guildMemberRemove', handleMemberRemove);

// ── Error handling ──────────────────────────────────────────────
client.on('error', err => console.error('[CLIENT ERROR]', err));
client.on('warn', info => console.warn('[CLIENT WARN]', info));
process.on('unhandledRejection', err => console.error('[UNHANDLED REJECTION]', err));
process.on('uncaughtException', err => { console.error('[UNCAUGHT EXCEPTION]', err); process.exit(1); });

// ── Login ───────────────────────────────────────────────────────
client.login(process.env.DISCORD_TOKEN);



================================================================================
FILE: discord-bot/package.json
================================================================================

{
  "name": "sparky-moderation-bot",
  "version": "1.0.0",
  "description": "Full-featured Discord moderation bot for Sparky AI",
  "main": "index.js",
  "scripts": {
    "start": "node index.js",
    "dev": "node --watch index.js"
  },
  "dependencies": {
    "discord.js": "^14.16.3",
    "dotenv": "^16.4.5"
  },
  "engines": {
    "node": ">=18.0.0"
  }
}



================================================================================
FILE: discord-bot/railway.toml
================================================================================

[build]
builder = "NIXPACKS"

[deploy]
startCommand = "node index.js"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10



================================================================================
FILE: discord-bot/events/handlers.js
================================================================================

const { EmbedBuilder, Events, PermissionFlagsBits } = require('discord.js');
const db = require('../utils/database');
const { commands } = require('../commands/moderation');
const {
  successEmbed, errorEmbed, warnEmbed, infoEmbed, modEmbed,
  resolveUser, accountAgeDays, sendLog
} = require('../utils/helpers');
const { applyChatban, removeChatban } = require('../utils/chatban');

// ── Spam tracking (in-memory) ───────────────────────────────────
const spamMap = new Map(); // userId -> [timestamp, ...]

// ── Prefix check ───────────────────────────────────────────────
const PREFIXES = ['.', '?'];

// ═══════════════════════════════════════════════════════════════
//  MESSAGE CREATE
// ═══════════════════════════════════════════════════════════════
async function handleMessage(message) {
  if (message.author.bot || !message.guild) return;

  // ── Word filter ────────────────────────────────────────────
  const filterWords = db.getFilterWords(message.guild.id);
  if (filterWords.length) {
    const lower = message.content.toLowerCase();
    if (filterWords.some(w => lower.includes(w))) {
      await message.delete().catch(() => null);
      const warn = await message.channel.send({
        embeds: [warnEmbed('Message Filtered', `${message.author}, your message was removed for containing a banned word.`)]
      });
      setTimeout(() => warn.delete().catch(() => null), 5000);
      return;
    }
  }

  // ── Anti-spam: 6+ messages in 10s → 5min timeout ─────────
  const now = Date.now();
  const uid = message.author.id;
  if (!spamMap.has(uid)) spamMap.set(uid, []);
  const timestamps = spamMap.get(uid).filter(t => now - t < 10000);
  timestamps.push(now);
  spamMap.set(uid, timestamps);

  if (timestamps.length >= 6) {
    spamMap.set(uid, []);
    const member = message.member;
    if (member && !member.permissions.has(PermissionFlagsBits.ManageMessages)) {
      try {
        await member.timeout(5 * 60 * 1000, 'Auto: spam detection (6+ messages in 10s)');
        const embed = modEmbed('Auto Mute (Spam)', message.client.user, message.author, 'Spam detection triggered', { Duration: '5 minutes' });
        embed.setColor(0xFEE75C);
        await sendLog(message.guild, embed, db);

        const warn = await message.channel.send({
          embeds: [warnEmbed('Spam Detected', `${message.author} has been muted for 5 minutes for spamming.`)]
        });
        setTimeout(() => warn.delete().catch(() => null), 6000);
      } catch {}
    }
    return;
  }

  // ── Prefix command dispatch ────────────────────────────────
  const prefix = PREFIXES.find(p => message.content.startsWith(p));
  if (!prefix) return;

  const args = message.content.slice(prefix.length).trim().split(/\s+/);
  const commandName = args.shift().toLowerCase();
  if (!commandName) return;

  const handler = commands[commandName];
  if (!handler) return;

  // Build ctx object
  const ctx = {
    client: message.client,
    guild: message.guild,
    channel: message.channel,
    member: message.member,
    user: message.author,
    args,
    message,
    reply: (opts) => message.reply(opts)
  };

  try {
    await handler(ctx);
  } catch (err) {
    console.error(`[CMD ERROR] ${commandName}:`, err);
    message.reply({ embeds: [errorEmbed('Error', `An error occurred: ${err.message}`)] }).catch(() => null);
  }
}

// ═══════════════════════════════════════════════════════════════
//  INTERACTION CREATE (slash commands + buttons)
// ═══════════════════════════════════════════════════════════════
async function handleInteraction(interaction) {
  // ── Slash commands ─────────────────────────────────────────
  if (interaction.isChatInputCommand()) {
    const { commandName } = interaction;
    const handler = commands[commandName];
    if (!handler) return;

    await interaction.deferReply({ ephemeral: false }).catch(() => null);

    const args = buildArgsFromSlash(interaction);

    const ctx = {
      client: interaction.client,
      guild: interaction.guild,
      channel: interaction.channel,
      member: interaction.member,
      user: interaction.user,
      args,
      interaction,
      reply: async (opts) => {
        try {
          if (interaction.deferred || interaction.replied) {
            return await interaction.editReply(opts);
          }
          return await interaction.reply(opts);
        } catch {}
      }
    };

    try {
      await handler(ctx);
    } catch (err) {
      console.error(`[SLASH ERROR] ${commandName}:`, err);
      ctx.reply({ embeds: [errorEmbed('Error', err.message)], ephemeral: true }).catch(() => null);
    }
  }

  // ── Chatban review buttons ─────────────────────────────────
  if (interaction.isButton()) {
    const [prefix, action, userId] = interaction.customId.split('_');
    if (prefix !== 'cbr') return;

    if (!interaction.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
      return interaction.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')], ephemeral: true });
    }

    const user = await interaction.client.users.fetch(userId).catch(() => null);
    if (!user) return interaction.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')], ephemeral: true });

    await interaction.deferUpdate().catch(() => null);

    if (action === 'remove') {
      await removeChatban(interaction.guild, userId);
      db.addModAction(interaction.guild.id, userId, { type: 'UNCHATBAN', moderatorId: interaction.user.id, reason: 'Review panel: removed' });
      await interaction.followUp({ embeds: [successEmbed('Chatban Removed', `${user.tag}'s chatban has been lifted.`)], ephemeral: false });
      await sendLog(interaction.guild, modEmbed('Chatban Removed (Panel)', interaction.user, user, 'Review panel decision'), db);

    } else if (action === 'increase') {
      // Extend to permanent (remove expiry)
      const existing = db.getChatban(interaction.guild.id, userId);
      if (existing) {
        existing.expiresAt = null;
        db.setChatban(interaction.guild.id, userId, existing);
      } else {
        await applyChatban(interaction.guild, userId, 'Review panel: increased', interaction.user.id);
      }
      await interaction.followUp({ embeds: [warnEmbed('Ban Increased', `${user.tag}'s chatban has been made permanent.`)], ephemeral: false });

    } else if (action === 'decrease') {
      // Reduce to 1 day from now
      const newExpiry = new Date(Date.now() + 24 * 60 * 60 * 1000);
      const existing = db.getChatban(interaction.guild.id, userId);
      if (existing) {
        existing.expiresAt = newExpiry.toISOString();
        db.setChatban(interaction.guild.id, userId, existing);
      }
      await interaction.followUp({ embeds: [successEmbed('Ban Decreased', `${user.tag}'s chatban reduced to 1 day.`)], ephemeral: false });

    } else if (action === 'keep') {
      await interaction.followUp({ embeds: [infoEmbed('No Change', `${user.tag}'s chatban has been kept as-is.`)], ephemeral: true });
    }
  }
}

// ── Build args array from slash interaction options ─────────────
function buildArgsFromSlash(interaction) {
  const args = [];
  const user = interaction.options.getUser?.('user') || interaction.options.getMember?.('user');
  const target = interaction.options.getUser?.('target');
  const role = interaction.options.getRole?.('role');

  if (user) args.push(user.id);
  else if (target) args.push(target.id);

  const duration = interaction.options.getString?.('duration');
  if (duration) args.push(duration);

  const reason = interaction.options.getString?.('reason');
  if (reason) args.push(reason);

  const amount = interaction.options.getInteger?.('amount');
  if (amount) args[0] = String(amount); // purge case

  const channel = interaction.options.getChannel?.('channel');
  if (channel) args[0] = channel.id;

  const word = interaction.options.getString?.('word');
  const subcommand = interaction.options.getSubcommand?.(false);
  if (subcommand) { args.unshift(subcommand); if (word) args.push(word); }

  if (role) args.push(role.id);

  const nickname = interaction.options.getString?.('nickname');
  if (nickname) args.push(nickname);

  return args;
}

// ═══════════════════════════════════════════════════════════════
//  GUILD MEMBER ADD
// ═══════════════════════════════════════════════════════════════
async function handleMemberAdd(member) {
  const cfg = db.getConfig(member.guild.id);
  if (!cfg.logsChannelId) return;

  const ch = member.guild.channels.cache.get(cfg.logsChannelId);
  if (!ch) return;

  const ageDays = accountAgeDays(member.user);
  const embed = new EmbedBuilder()
    .setColor(ageDays < 7 ? 0xFEE75C : 0x57F287)
    .setTitle(`📥 Member Joined${ageDays < 7 ? ' ⚠️ NEW ACCOUNT' : ''}`)
    .setThumbnail(member.user.displayAvatarURL())
    .addFields(
      { name: 'User', value: `${member.user.tag} (\`${member.user.id}\`)`, inline: true },
      { name: 'Account Age', value: `${ageDays} days`, inline: true },
      { name: 'Created', value: `<t:${Math.floor(member.user.createdTimestamp / 1000)}:R>`, inline: true },
      { name: 'Total Members', value: `${member.guild.memberCount}`, inline: true }
    )
    .setTimestamp();

  if (ageDays < 7) embed.setDescription('⚠️ **This account is less than 7 days old!**');

  ch.send({ embeds: [embed] }).catch(() => null);
}

// ═══════════════════════════════════════════════════════════════
//  GUILD MEMBER REMOVE
// ═══════════════════════════════════════════════════════════════
async function handleMemberRemove(member) {
  const cfg = db.getConfig(member.guild.id);
  if (!cfg.logsChannelId) return;

  const ch = member.guild.channels.cache.get(cfg.logsChannelId);
  if (!ch) return;

  const embed = new EmbedBuilder()
    .setColor(0xED4245)
    .setTitle('📤 Member Left')
    .setThumbnail(member.user.displayAvatarURL())
    .addFields(
      { name: 'User', value: `${member.user.tag} (\`${member.user.id}\`)`, inline: true },
      { name: 'Joined', value: member.joinedAt ? `<t:${Math.floor(member.joinedTimestamp / 1000)}:R>` : 'Unknown', inline: true },
      { name: 'Total Members', value: `${member.guild.memberCount}`, inline: true }
    )
    .setTimestamp();

  ch.send({ embeds: [embed] }).catch(() => null);
}

module.exports = { handleMessage, handleInteraction, handleMemberAdd, handleMemberRemove };



================================================================================
FILE: discord-bot/utils/chatban.js
================================================================================

const { PermissionFlagsBits } = require('discord.js');
const db = require('./database');

const CHATBAN_DENIED = [
  PermissionFlagsBits.SendMessages,
  PermissionFlagsBits.AddReactions,
  PermissionFlagsBits.CreatePublicThreads,
  PermissionFlagsBits.CreatePrivateThreads,
  PermissionFlagsBits.SendMessagesInThreads
];

async function applyChatban(guild, userId, reason, moderatorId, duration = null) {
  const member = await guild.members.fetch(userId).catch(() => null);
  if (!member) return false;

  const channels = guild.channels.cache.filter(c =>
    c.isTextBased() && c.permissionsFor && !c.isThread()
  );

  for (const [, channel] of channels) {
    try {
      await channel.permissionOverwrites.edit(userId, {
        SendMessages: false,
        AddReactions: false,
        CreatePublicThreads: false,
        CreatePrivateThreads: false,
        SendMessagesInThreads: false
      });
    } catch {}
  }

  db.setChatban(guild.id, userId, {
    moderatorId,
    reason,
    appliedAt: new Date().toISOString(),
    expiresAt: duration ? new Date(Date.now() + duration).toISOString() : null
  });

  return true;
}

async function removeChatban(guild, userId) {
  const member = await guild.members.fetch(userId).catch(() => null);
  const channels = guild.channels.cache.filter(c =>
    c.isTextBased() && c.permissionsFor && !c.isThread()
  );

  for (const [, channel] of channels) {
    try {
      const overwrite = channel.permissionOverwrites.cache.get(userId);
      if (overwrite) await overwrite.delete();
    } catch {}
  }

  db.removeChatban(guild.id, userId);
  return true;
}

module.exports = { applyChatban, removeChatban };



================================================================================
FILE: discord-bot/utils/database.js
================================================================================

const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');

// Ensure data directory exists
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

function loadData(filename) {
  const filepath = path.join(DATA_DIR, filename);
  if (!fs.existsSync(filepath)) return {};
  try {
    return JSON.parse(fs.readFileSync(filepath, 'utf8'));
  } catch {
    return {};
  }
}

function saveData(filename, data) {
  const filepath = path.join(DATA_DIR, filename);
  fs.writeFileSync(filepath, JSON.stringify(data, null, 2));
}

// --- WARNINGS ---
function getWarnings(guildId, userId) {
  const data = loadData('warnings.json');
  return data[guildId]?.[userId] || [];
}

function addWarning(guildId, userId, moderatorId, reason) {
  const data = loadData('warnings.json');
  if (!data[guildId]) data[guildId] = {};
  if (!data[guildId][userId]) data[guildId][userId] = [];
  const warning = {
    id: Date.now(),
    moderatorId,
    reason,
    timestamp: new Date().toISOString()
  };
  data[guildId][userId].push(warning);
  saveData('warnings.json', data);
  return data[guildId][userId];
}

function removeWarning(guildId, userId, warningId) {
  const data = loadData('warnings.json');
  if (!data[guildId]?.[userId]) return false;
  const before = data[guildId][userId].length;
  data[guildId][userId] = data[guildId][userId].filter(w => w.id !== warningId);
  saveData('warnings.json', data);
  return data[guildId][userId].length < before;
}

function clearWarnings(guildId, userId) {
  const data = loadData('warnings.json');
  if (!data[guildId]) return;
  data[guildId][userId] = [];
  saveData('warnings.json', data);
}

// --- MOD ACTIONS LOG ---
function addModAction(guildId, userId, action) {
  const data = loadData('modactions.json');
  if (!data[guildId]) data[guildId] = {};
  if (!data[guildId][userId]) data[guildId][userId] = [];
  data[guildId][userId].push({ ...action, timestamp: new Date().toISOString() });
  saveData('modactions.json', data);
}

function getModActions(guildId, userId) {
  const data = loadData('modactions.json');
  return data[guildId]?.[userId] || [];
}

// --- NOTES ---
function addNote(guildId, userId, moderatorId, note) {
  const data = loadData('notes.json');
  if (!data[guildId]) data[guildId] = {};
  if (!data[guildId][userId]) data[guildId][userId] = [];
  const entry = { id: Date.now(), moderatorId, note, timestamp: new Date().toISOString() };
  data[guildId][userId].push(entry);
  saveData('notes.json', data);
  return entry;
}

function getNotes(guildId, userId) {
  const data = loadData('notes.json');
  return data[guildId]?.[userId] || [];
}

function removeNote(guildId, userId, noteId) {
  const data = loadData('notes.json');
  if (!data[guildId]?.[userId]) return false;
  const before = data[guildId][userId].length;
  data[guildId][userId] = data[guildId][userId].filter(n => n.id !== noteId);
  saveData('notes.json', data);
  return data[guildId][userId].length < before;
}

// --- CONFIG (logs channel, etc.) ---
function getConfig(guildId) {
  const data = loadData('config.json');
  return data[guildId] || {};
}

function setConfig(guildId, key, value) {
  const data = loadData('config.json');
  if (!data[guildId]) data[guildId] = {};
  data[guildId][key] = value;
  saveData('config.json', data);
}

// --- FILTER WORDS ---
function getFilterWords(guildId) {
  const data = loadData('filter.json');
  return data[guildId] || [];
}

function addFilterWord(guildId, word) {
  const data = loadData('filter.json');
  if (!data[guildId]) data[guildId] = [];
  if (!data[guildId].includes(word.toLowerCase())) {
    data[guildId].push(word.toLowerCase());
    saveData('filter.json', data);
    return true;
  }
  return false;
}

function removeFilterWord(guildId, word) {
  const data = loadData('filter.json');
  if (!data[guildId]) return false;
  const before = data[guildId].length;
  data[guildId] = data[guildId].filter(w => w !== word.toLowerCase());
  saveData('filter.json', data);
  return data[guildId].length < before;
}

// --- CHATBANS ---
function setChatban(guildId, userId, data_) {
  const data = loadData('chatbans.json');
  if (!data[guildId]) data[guildId] = {};
  data[guildId][userId] = data_;
  saveData('chatbans.json', data);
}

function getChatban(guildId, userId) {
  const data = loadData('chatbans.json');
  return data[guildId]?.[userId] || null;
}

function removeChatban(guildId, userId) {
  const data = loadData('chatbans.json');
  if (!data[guildId]) return;
  delete data[guildId][userId];
  saveData('chatbans.json', data);
}

module.exports = {
  getWarnings, addWarning, removeWarning, clearWarnings,
  addModAction, getModActions,
  addNote, getNotes, removeNote,
  getConfig, setConfig,
  getFilterWords, addFilterWord, removeFilterWord,
  setChatban, getChatban, removeChatban
};



================================================================================
FILE: discord-bot/utils/helpers.js
================================================================================

const { EmbedBuilder, PermissionFlagsBits } = require('discord.js');

// ── Colour palette ──────────────────────────────────────────────
const COLORS = {
  success: 0x57F287,
  error:   0xED4245,
  warn:    0xFEE75C,
  info:    0x5865F2,
  mod:     0xEB459E,
  log:     0x23272A
};

// ── Embed builders ──────────────────────────────────────────────
function successEmbed(title, description) {
  return new EmbedBuilder().setColor(COLORS.success).setTitle(`✅ ${title}`).setDescription(description).setTimestamp();
}

function errorEmbed(title, description) {
  return new EmbedBuilder().setColor(COLORS.error).setTitle(`❌ ${title}`).setDescription(description).setTimestamp();
}

function warnEmbed(title, description) {
  return new EmbedBuilder().setColor(COLORS.warn).setTitle(`⚠️ ${title}`).setDescription(description).setTimestamp();
}

function infoEmbed(title, description) {
  return new EmbedBuilder().setColor(COLORS.info).setTitle(`ℹ️ ${title}`).setDescription(description).setTimestamp();
}

function modEmbed(action, moderator, target, reason, extra = {}) {
  const embed = new EmbedBuilder()
    .setColor(COLORS.mod)
    .setTitle(`🔨 ${action}`)
    .addFields(
      { name: 'Target', value: `${target.tag || target} (${target.id || target})`, inline: true },
      { name: 'Moderator', value: `${moderator.tag || moderator}`, inline: true },
      { name: 'Reason', value: reason || 'No reason provided' }
    )
    .setTimestamp();
  for (const [k, v] of Object.entries(extra)) {
    embed.addFields({ name: k, value: String(v), inline: true });
  }
  return embed;
}

// ── Resolve a user from mention, ID, or tag ──────────────────────
async function resolveUser(client, guild, input) {
  if (!input) return null;
  // Strip mention formatting
  const cleaned = input.replace(/[<@!>]/g, '').trim();
  // Try member first (within guild)
  try {
    const member = await guild.members.fetch(cleaned).catch(() => null);
    if (member) return { user: member.user, member };
  } catch {}
  // Try fetching user globally
  try {
    const user = await client.users.fetch(cleaned).catch(() => null);
    if (user) return { user, member: null };
  } catch {}
  return null;
}

// ── Permission check helper ──────────────────────────────────────
function hasModPermission(member) {
  return member.permissions.has(PermissionFlagsBits.ModerateMembers) ||
         member.permissions.has(PermissionFlagsBits.BanMembers) ||
         member.permissions.has(PermissionFlagsBits.KickMembers) ||
         member.permissions.has(PermissionFlagsBits.Administrator);
}

function hasAdminPermission(member) {
  return member.permissions.has(PermissionFlagsBits.Administrator) ||
         member.permissions.has(PermissionFlagsBits.ManageGuild);
}

// ── Format duration ─────────────────────────────────────────────
function formatDuration(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours   = Math.floor(minutes / 60);
  const days    = Math.floor(hours / 24);
  if (days > 0)    return `${days}d ${hours % 24}h`;
  if (hours > 0)   return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${seconds}s`;
}

// ── Format timestamp to readable string ─────────────────────────
function formatDate(date) {
  return new Date(date).toUTCString();
}

// ── Account age warning ─────────────────────────────────────────
function accountAgeDays(user) {
  return Math.floor((Date.now() - user.createdTimestamp) / (1000 * 60 * 60 * 24));
}

// ── Send to log channel ─────────────────────────────────────────
async function sendLog(guild, embed, db) {
  const cfg = db.getConfig(guild.id);
  if (!cfg.logsChannelId) return;
  const ch = guild.channels.cache.get(cfg.logsChannelId);
  if (ch) {
    try { await ch.send({ embeds: [embed] }); } catch {}
  }
}

module.exports = {
  COLORS, successEmbed, errorEmbed, warnEmbed, infoEmbed, modEmbed,
  resolveUser, hasModPermission, hasAdminPermission,
  formatDuration, formatDate, accountAgeDays, sendLog
};



================================================================================
FILE: discord-bot/utils/registerCommands.js
================================================================================

const { REST, Routes, SlashCommandBuilder, PermissionFlagsBits } = require('discord.js');
require('dotenv').config();

const commands = [
  // Warn
  new SlashCommandBuilder().setName('warn').setDescription('Warn a user')
    .addUserOption(o => o.setName('user').setDescription('User to warn').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Reason for the warning')),

  // Warnings
  new SlashCommandBuilder().setName('warnings').setDescription('View warnings for a user')
    .addUserOption(o => o.setName('user').setDescription('User to check').setRequired(true)),

  // Delwarn
  new SlashCommandBuilder().setName('delwarn').setDescription('Delete a warning')
    .addUserOption(o => o.setName('user').setDescription('User').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Warning ID').setRequired(true)),

  // Chatban
  new SlashCommandBuilder().setName('chatban').setDescription('Chatban a user')
    .addUserOption(o => o.setName('user').setDescription('User to chatban').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Reason')),

  // Unchatban
  new SlashCommandBuilder().setName('unchatban').setDescription('Remove a chatban')
    .addUserOption(o => o.setName('user').setDescription('User to unchatban').setRequired(true)),

  // Mute
  new SlashCommandBuilder().setName('mute').setDescription('Timeout/mute a user')
    .addUserOption(o => o.setName('user').setDescription('User to mute').setRequired(true))
    .addStringOption(o => o.setName('duration').setDescription('Duration (e.g. 10m, 1h, 2d)').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Reason')),

  // Unmute
  new SlashCommandBuilder().setName('unmute').setDescription('Remove a timeout from a user')
    .addUserOption(o => o.setName('user').setDescription('User to unmute').setRequired(true)),

  // Kick
  new SlashCommandBuilder().setName('kick').setDescription('Kick a member')
    .addUserOption(o => o.setName('user').setDescription('User to kick').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Reason')),

  // Ban
  new SlashCommandBuilder().setName('ban').setDescription('Ban a user')
    .addUserOption(o => o.setName('user').setDescription('User to ban').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Reason')),

  // Unban
  new SlashCommandBuilder().setName('unban').setDescription('Unban a user by ID')
    .addStringOption(o => o.setName('reason').setDescription('User ID to unban').setRequired(true)),

  // Usercheck
  new SlashCommandBuilder().setName('usercheck').setDescription('View user info and mod history')
    .addUserOption(o => o.setName('user').setDescription('User to check').setRequired(true)),

  // Note
  new SlashCommandBuilder().setName('note').setDescription('Add a private mod note to a user')
    .addUserOption(o => o.setName('user').setDescription('User').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Note text').setRequired(true)),

  // Notes
  new SlashCommandBuilder().setName('notes').setDescription('View notes for a user')
    .addUserOption(o => o.setName('user').setDescription('User').setRequired(true)),

  // Delnote
  new SlashCommandBuilder().setName('delnote').setDescription('Delete a note')
    .addUserOption(o => o.setName('user').setDescription('User').setRequired(true))
    .addStringOption(o => o.setName('reason').setDescription('Note ID').setRequired(true)),

  // Lock
  new SlashCommandBuilder().setName('lock').setDescription('Lock the current channel'),

  // Unlock
  new SlashCommandBuilder().setName('unlock').setDescription('Unlock the current channel'),

  // Lockdown
  new SlashCommandBuilder().setName('lockdown').setDescription('Lock all channels'),

  // Unlockall
  new SlashCommandBuilder().setName('unlockall').setDescription('Unlock all channels'),

  // Nuke
  new SlashCommandBuilder().setName('nuke').setDescription('Clone and delete current channel'),

  // Nickname
  new SlashCommandBuilder().setName('nickname').setDescription('Force change a user\'s nickname')
    .addUserOption(o => o.setName('user').setDescription('User').setRequired(true))
    .addStringOption(o => o.setName('nickname').setDescription('New nickname (leave empty to reset)')),

  // Role
  new SlashCommandBuilder().setName('role').setDescription('Add or remove a role from a user')
    .addUserOption(o => o.setName('user').setDescription('User').setRequired(true))
    .addRoleOption(o => o.setName('role').setDescription('Role to add/remove').setRequired(true)),

  // Purge
  new SlashCommandBuilder().setName('purge').setDescription('Bulk delete messages')
    .addIntegerOption(o => o.setName('amount').setDescription('Number of messages (1-100)').setRequired(true).setMinValue(1).setMaxValue(100)),

  // Slowmode
  new SlashCommandBuilder().setName('slowmode').setDescription('Set channel slowmode')
    .addIntegerOption(o => o.setName('amount').setDescription('Seconds (0 to disable)').setRequired(true).setMinValue(0).setMaxValue(21600)),

  // Filter
  new SlashCommandBuilder().setName('filter').setDescription('Manage word filter')
    .addSubcommand(s => s.setName('add').setDescription('Add a word to filter').addStringOption(o => o.setName('word').setDescription('Word to filter').setRequired(true)))
    .addSubcommand(s => s.setName('remove').setDescription('Remove a word from filter').addStringOption(o => o.setName('word').setDescription('Word to remove').setRequired(true)))
    .addSubcommand(s => s.setName('list').setDescription('List all filtered words')),

  // Avatar
  new SlashCommandBuilder().setName('avatar').setDescription('Show a user\'s avatar')
    .addUserOption(o => o.setName('user').setDescription('User (defaults to yourself)')),

  // Logschannel
  new SlashCommandBuilder().setName('logschannel').setDescription('Set the mod logs channel')
    .addChannelOption(o => o.setName('channel').setDescription('Channel for mod logs').setRequired(true)),

  // Serverinfo
  new SlashCommandBuilder().setName('serverinfo').setDescription('Show server information'),

  // Review panel
  new SlashCommandBuilder().setName('reviewpanel').setDescription('Open chatban review panel for a user')
    .addUserOption(o => o.setName('user').setDescription('User to review').setRequired(true)),

  // Help
  new SlashCommandBuilder().setName('help').setDescription('Show all commands'),
].map(c => c.toJSON());

async function registerCommands() {
  const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
  const guildId = process.env.GUILD_ID;

  console.log('[DEPLOY] Registering slash commands...');
  try {
    if (guildId) {
      // Guild commands (instant, for development)
      await rest.put(Routes.applicationGuildCommands(
        // We grab app ID from a quick auth check
        (await rest.get(Routes.user('@me'))).id,
        guildId
      ), { body: commands });
      console.log(`[DEPLOY] Registered ${commands.length} guild commands to ${guildId}`);
    } else {
      // Global commands (up to 1h to propagate)
      const appId = (await rest.get(Routes.user('@me'))).id;
      await rest.put(Routes.applicationCommands(appId), { body: commands });
      console.log(`[DEPLOY] Registered ${commands.length} global commands`);
    }
  } catch (err) {
    console.error('[DEPLOY] Error registering commands:', err);
  }
}

module.exports = { registerCommands };



================================================================================
FILE: discord-bot/commands/moderation.js
================================================================================

const {
  EmbedBuilder, PermissionFlagsBits, ActionRowBuilder,
  ButtonBuilder, ButtonStyle, ChannelType
} = require('discord.js');
const db = require('../utils/database');
const {
  successEmbed, errorEmbed, warnEmbed, infoEmbed, modEmbed,
  resolveUser, hasModPermission, hasAdminPermission,
  formatDuration, formatDate, accountAgeDays, sendLog
} = require('../utils/helpers');
const { applyChatban, removeChatban } = require('../utils/chatban');

// ═══════════════════════════════════════════════════════════════
//  COMMAND REGISTRY
// ═══════════════════════════════════════════════════════════════
const commands = {};

function cmd(name, aliases, handler) {
  commands[name] = handler;
  for (const alias of aliases) commands[alias] = handler;
}

// ───────────────────────────────────────────────────────────────
//  WARN
// ───────────────────────────────────────────────────────────────
cmd('warn', [], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const reason = ctx.args.slice(1).join(' ') || 'No reason provided';
  const { user } = resolved;

  const warnings = db.addWarning(ctx.guild.id, user.id, ctx.member.id, reason);
  const count = warnings.length;

  db.addModAction(ctx.guild.id, user.id, { type: 'WARN', moderatorId: ctx.member.id, reason });

  // Auto-escalation
  let escalationMsg = '';
  if (count === 3) {
    await applyChatban(ctx.guild, user.id, 'Auto: 3 warnings', ctx.client.user.id, 24 * 60 * 60 * 1000);
    escalationMsg = '\n⚡ **Auto-escalation:** 1-day chatban applied.';
  } else if (count === 5) {
    await applyChatban(ctx.guild, user.id, 'Auto: 5 warnings', ctx.client.user.id, 7 * 24 * 60 * 60 * 1000);
    escalationMsg = '\n⚡ **Auto-escalation:** 1-week chatban applied.';
    try {
      await user.send({
        embeds: [warnEmbed('Final Warning', `You have received 5 warnings in **${ctx.guild.name}**. Further violations will result in a temporary ban.`)]
      });
    } catch {}
  } else if (count >= 6) {
    const banExpiry = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    try {
      await ctx.guild.members.ban(user.id, { reason: 'Auto: 6 warnings - 1 month temp ban', deleteMessageSeconds: 0 });
      db.addModAction(ctx.guild.id, user.id, { type: 'TEMPBAN', moderatorId: ctx.client.user.id, reason: 'Auto: 6 warnings', expiresAt: banExpiry.toISOString() });
    } catch {}
    escalationMsg = '\n⚡ **Auto-escalation:** 1-month temporary ban applied.';
  }

  const embed = modEmbed('Warning Issued', ctx.member.user, user, reason, { 'Warning Count': `${count}` });
  embed.setDescription((embed.data.description || '') + escalationMsg);

  await sendLog(ctx.guild, embed, db);
  ctx.reply({ embeds: [embed] });

  // DM the warned user
  try {
    await user.send({
      embeds: [warnEmbed('You were warned', `**Server:** ${ctx.guild.name}\n**Reason:** ${reason}\n**Total Warnings:** ${count}`)]
    });
  } catch {}
});

// ───────────────────────────────────────────────────────────────
//  WARNINGS (view)
// ───────────────────────────────────────────────────────────────
cmd('warnings', ['infractions'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const warnings = db.getWarnings(ctx.guild.id, resolved.user.id);
  if (!warnings.length) return ctx.reply({ embeds: [infoEmbed('No Warnings', `${resolved.user.tag} has no warnings.`)] });

  const embed = new EmbedBuilder()
    .setColor(0xFEE75C)
    .setTitle(`⚠️ Warnings for ${resolved.user.tag}`)
    .setThumbnail(resolved.user.displayAvatarURL())
    .setDescription(warnings.map((w, i) =>
      `**#${i + 1}** • <t:${Math.floor(new Date(w.timestamp).getTime() / 1000)}:R>\n> ${w.reason}\n> *by <@${w.moderatorId}>* • ID: \`${w.id}\``
    ).join('\n\n'))
    .setFooter({ text: `${warnings.length} total warning(s)` })
    .setTimestamp();

  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  DELWARN
// ───────────────────────────────────────────────────────────────
cmd('delwarn', ['removewarn'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });
  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });
  const warnId = parseInt(ctx.args[1]);
  if (!warnId) return ctx.reply({ embeds: [errorEmbed('Invalid ID', 'Provide a warning ID.')] });
  const removed = db.removeWarning(ctx.guild.id, resolved.user.id, warnId);
  ctx.reply({ embeds: [removed ? successEmbed('Warning Removed', `Removed warning \`${warnId}\` from ${resolved.user.tag}.`) : errorEmbed('Not Found', 'Warning ID not found.')] });
});

// ───────────────────────────────────────────────────────────────
//  CHATBAN
// ───────────────────────────────────────────────────────────────
cmd('chatban', ['cb'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const reason = ctx.args.slice(1).join(' ') || 'No reason provided';
  const { user } = resolved;

  await applyChatban(ctx.guild, user.id, reason, ctx.member.id);
  db.addModAction(ctx.guild.id, user.id, { type: 'CHATBAN', moderatorId: ctx.member.id, reason });

  const embed = modEmbed('Chatban Applied', ctx.member.user, user, reason);
  await sendLog(ctx.guild, embed, db);
  ctx.reply({ embeds: [embed] });

  try {
    await user.send({ embeds: [errorEmbed('Chatbanned', `You have been chatbanned in **${ctx.guild.name}**.\n**Reason:** ${reason}`)] });
  } catch {}
});

// ───────────────────────────────────────────────────────────────
//  UNCHATBAN
// ───────────────────────────────────────────────────────────────
cmd('unchatban', ['uncb'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const { user } = resolved;
  await removeChatban(ctx.guild, user.id);
  db.addModAction(ctx.guild.id, user.id, { type: 'UNCHATBAN', moderatorId: ctx.member.id });

  const embed = modEmbed('Chatban Removed', ctx.member.user, user, 'Chatban lifted');
  await sendLog(ctx.guild, embed, db);
  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  MUTE (timeout)
// ───────────────────────────────────────────────────────────────
cmd('mute', ['timeout'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved?.member) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that member.')] });

  // Parse duration: 10m, 1h, 2d etc.
  const durationStr = ctx.args[1] || '10m';
  const duration = parseDuration(durationStr);
  if (!duration) return ctx.reply({ embeds: [errorEmbed('Invalid Duration', 'Use format: 10m, 1h, 2d (max 28d)')] });

  const reason = ctx.args.slice(2).join(' ') || 'No reason provided';
  const { user, member } = resolved;

  try {
    await member.timeout(duration, reason);
  } catch (e) {
    return ctx.reply({ embeds: [errorEmbed('Failed', `Could not mute: ${e.message}`)] });
  }

  db.addModAction(ctx.guild.id, user.id, { type: 'MUTE', moderatorId: ctx.member.id, reason, duration: durationStr });

  const embed = modEmbed('Member Muted', ctx.member.user, user, reason, { Duration: durationStr });
  await sendLog(ctx.guild, embed, db);
  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  UNMUTE
// ───────────────────────────────────────────────────────────────
cmd('unmute', ['untimeout'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved?.member) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that member.')] });

  const { user, member } = resolved;
  try {
    await member.timeout(null, 'Mute removed');
  } catch (e) {
    return ctx.reply({ embeds: [errorEmbed('Failed', `Could not unmute: ${e.message}`)] });
  }

  db.addModAction(ctx.guild.id, user.id, { type: 'UNMUTE', moderatorId: ctx.member.id });
  const embed = modEmbed('Member Unmuted', ctx.member.user, user, 'Mute removed');
  await sendLog(ctx.guild, embed, db);
  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  KICK
// ───────────────────────────────────────────────────────────────
cmd('kick', [], async (ctx) => {
  if (!ctx.member.permissions.has(PermissionFlagsBits.KickMembers)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Kick Members permission.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved?.member) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that member.')] });

  const reason = ctx.args.slice(1).join(' ') || 'No reason provided';
  const { user, member } = resolved;

  try {
    await member.kick(reason);
  } catch (e) {
    return ctx.reply({ embeds: [errorEmbed('Failed', `Could not kick: ${e.message}`)] });
  }

  db.addModAction(ctx.guild.id, user.id, { type: 'KICK', moderatorId: ctx.member.id, reason });
  const embed = modEmbed('Member Kicked', ctx.member.user, user, reason);
  await sendLog(ctx.guild, embed, db);
  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  BAN
// ───────────────────────────────────────────────────────────────
cmd('ban', [], async (ctx) => {
  if (!ctx.member.permissions.has(PermissionFlagsBits.BanMembers)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Ban Members permission.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const reason = ctx.args.slice(1).join(' ') || 'No reason provided';
  const { user } = resolved;

  try {
    await ctx.guild.members.ban(user.id, { reason, deleteMessageSeconds: 604800 });
  } catch (e) {
    return ctx.reply({ embeds: [errorEmbed('Failed', `Could not ban: ${e.message}`)] });
  }

  db.addModAction(ctx.guild.id, user.id, { type: 'BAN', moderatorId: ctx.member.id, reason });
  const embed = modEmbed('Member Banned', ctx.member.user, user, reason);
  await sendLog(ctx.guild, embed, db);

  // Ghost ping owner
  const cfg = db.getConfig(ctx.guild.id);
  if (cfg.logsChannelId && process.env.OWNER_ID) {
    const ch = ctx.guild.channels.cache.get(cfg.logsChannelId);
    if (ch) {
      const ping = await ch.send(`<@${process.env.OWNER_ID}>`).catch(() => null);
      if (ping) ping.delete().catch(() => null);
    }
  }

  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  UNBAN
// ───────────────────────────────────────────────────────────────
cmd('unban', [], async (ctx) => {
  if (!ctx.member.permissions.has(PermissionFlagsBits.BanMembers)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Ban Members permission.')] });

  const userId = ctx.args[0]?.replace(/[<@!>]/g, '');
  if (!userId) return ctx.reply({ embeds: [errorEmbed('Missing User', 'Provide a user ID to unban.')] });

  const reason = ctx.args.slice(1).join(' ') || 'No reason provided';

  try {
    const ban = await ctx.guild.bans.fetch(userId).catch(() => null);
    if (!ban) return ctx.reply({ embeds: [errorEmbed('Not Banned', 'That user is not banned.')] });
    await ctx.guild.members.unban(userId, reason);
  } catch (e) {
    return ctx.reply({ embeds: [errorEmbed('Failed', `Could not unban: ${e.message}`)] });
  }

  const user = await ctx.client.users.fetch(userId).catch(() => ({ tag: userId, id: userId }));
  db.addModAction(ctx.guild.id, userId, { type: 'UNBAN', moderatorId: ctx.member.id, reason });
  const embed = modEmbed('Member Unbanned', ctx.member.user, user, reason);
  await sendLog(ctx.guild, embed, db);
  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  USERCHECK
// ───────────────────────────────────────────────────────────────
cmd('usercheck', ['uc', 'check', 'info'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0] || ctx.member.id);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const { user, member } = resolved;
  const warnings = db.getWarnings(ctx.guild.id, user.id);
  const actions = db.getModActions(ctx.guild.id, user.id);
  const ageDays = accountAgeDays(user);

  const embed = new EmbedBuilder()
    .setColor(0x5865F2)
    .setTitle(`🔍 User Check: ${user.tag}`)
    .setThumbnail(user.displayAvatarURL({ dynamic: true, size: 256 }))
    .addFields(
      { name: '👤 User', value: `${user} (\`${user.id}\`)`, inline: true },
      { name: '📅 Account Created', value: `<t:${Math.floor(user.createdTimestamp / 1000)}:R>`, inline: true },
      { name: '📆 Account Age', value: `${ageDays} days ${ageDays < 7 ? '⚠️ NEW' : ''}`, inline: true }
    )
    .setTimestamp();

  if (member) {
    embed.addFields(
      { name: '📥 Joined Server', value: `<t:${Math.floor(member.joinedTimestamp / 1000)}:R>`, inline: true },
      { name: '🏷️ Roles', value: member.roles.cache.filter(r => r.id !== ctx.guild.id).map(r => r).join(', ') || 'None', inline: false }
    );
  }

  embed.addFields(
    { name: `⚠️ Warnings (${warnings.length})`, value: warnings.length ? warnings.slice(-3).map(w => `• ${w.reason} — <t:${Math.floor(new Date(w.timestamp).getTime() / 1000)}:R>`).join('\n') : 'None' },
    { name: `🔨 Recent Actions (${actions.length})`, value: actions.length ? actions.slice(-5).map(a => `• **${a.type}** — ${a.reason || ''} <t:${Math.floor(new Date(a.timestamp).getTime() / 1000)}:R>`).join('\n') : 'None' }
  );

  // Possible alts: accounts created within 24h of this one, in the same guild
  const within24h = ctx.guild.members.cache.filter(m =>
    m.id !== user.id &&
    Math.abs(m.user.createdTimestamp - user.createdTimestamp) < 24 * 60 * 60 * 1000
  );
  if (within24h.size > 0) {
    embed.addFields({ name: '🔁 Possible Alts', value: within24h.map(m => `${m.user.tag}`).slice(0, 10).join('\n') });
  }

  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  NOTE / NOTES
// ───────────────────────────────────────────────────────────────
cmd('note', [], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const noteText = ctx.args.slice(1).join(' ');
  if (!noteText) return ctx.reply({ embeds: [errorEmbed('Missing Note', 'Provide note text after the user.')] });

  const entry = db.addNote(ctx.guild.id, resolved.user.id, ctx.member.id, noteText);
  ctx.reply({ embeds: [successEmbed('Note Added', `Note added for ${resolved.user.tag}.\n> ${noteText}\nID: \`${entry.id}\``)] });
});

cmd('notes', [], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const notes = db.getNotes(ctx.guild.id, resolved.user.id);
  if (!notes.length) return ctx.reply({ embeds: [infoEmbed('No Notes', `No notes for ${resolved.user.tag}.`)] });

  const embed = new EmbedBuilder()
    .setColor(0x5865F2)
    .setTitle(`📝 Notes for ${resolved.user.tag}`)
    .setDescription(notes.map((n, i) =>
      `**#${i + 1}** by <@${n.moderatorId}> • <t:${Math.floor(new Date(n.timestamp).getTime() / 1000)}:R>\n> ${n.note}\n> ID: \`${n.id}\``
    ).join('\n\n'))
    .setTimestamp();

  ctx.reply({ embeds: [embed] });
});

cmd('delnote', [], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });
  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });
  const noteId = parseInt(ctx.args[1]);
  if (!noteId) return ctx.reply({ embeds: [errorEmbed('Invalid ID', 'Provide a note ID.')] });
  const removed = db.removeNote(ctx.guild.id, resolved.user.id, noteId);
  ctx.reply({ embeds: [removed ? successEmbed('Note Deleted', 'Note removed.') : errorEmbed('Not Found', 'Note ID not found.')] });
});

// ───────────────────────────────────────────────────────────────
//  LOCK / UNLOCK
// ───────────────────────────────────────────────────────────────
cmd('lock', [], async (ctx) => {
  if (!hasAdminPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Guild permission.')] });
  const channel = ctx.channel;
  try {
    await channel.permissionOverwrites.edit(ctx.guild.roles.everyone, { SendMessages: false });
    ctx.reply({ embeds: [successEmbed('Channel Locked', `${channel} is now locked.`)] });
    await sendLog(ctx.guild, modEmbed('Channel Locked', ctx.member.user, { tag: channel.name, id: channel.id }, 'Manual lock'), db);
  } catch (e) {
    ctx.reply({ embeds: [errorEmbed('Failed', e.message)] });
  }
});

cmd('unlock', [], async (ctx) => {
  if (!hasAdminPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Guild permission.')] });
  const channel = ctx.channel;
  try {
    await channel.permissionOverwrites.edit(ctx.guild.roles.everyone, { SendMessages: null });
    ctx.reply({ embeds: [successEmbed('Channel Unlocked', `${channel} is now unlocked.`)] });
    await sendLog(ctx.guild, modEmbed('Channel Unlocked', ctx.member.user, { tag: channel.name, id: channel.id }, 'Manual unlock'), db);
  } catch (e) {
    ctx.reply({ embeds: [errorEmbed('Failed', e.message)] });
  }
});

// ───────────────────────────────────────────────────────────────
//  LOCKDOWN
// ───────────────────────────────────────────────────────────────
cmd('lockdown', [], async (ctx) => {
  if (!hasAdminPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Guild permission.')] });

  const channels = ctx.guild.channels.cache.filter(c => c.isTextBased() && !c.isThread());
  let count = 0;
  for (const [, ch] of channels) {
    try {
      await ch.permissionOverwrites.edit(ctx.guild.roles.everyone, { SendMessages: false });
      count++;
    } catch {}
  }

  await sendLog(ctx.guild, modEmbed('🔒 SERVER LOCKDOWN', ctx.member.user, { tag: ctx.guild.name, id: ctx.guild.id }, `Locked ${count} channels`), db);
  ctx.reply({ embeds: [warnEmbed('Lockdown Active', `Locked **${count}** channels. Use \`.unlock\` in each or \`.unlockall\` to lift.`)] });
});

cmd('unlockall', [], async (ctx) => {
  if (!hasAdminPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Guild permission.')] });

  const channels = ctx.guild.channels.cache.filter(c => c.isTextBased() && !c.isThread());
  let count = 0;
  for (const [, ch] of channels) {
    try {
      await ch.permissionOverwrites.edit(ctx.guild.roles.everyone, { SendMessages: null });
      count++;
    } catch {}
  }

  ctx.reply({ embeds: [successEmbed('Lockdown Lifted', `Unlocked **${count}** channels.`)] });
});

// ───────────────────────────────────────────────────────────────
//  NUKE
// ───────────────────────────────────────────────────────────────
cmd('nuke', [], async (ctx) => {
  if (!hasAdminPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Guild permission.')] });

  const channel = ctx.channel;
  const pos = channel.position;
  const parent = channel.parentId;
  const overwrites = channel.permissionOverwrites.cache;
  const topic = channel.topic;
  const name = channel.name;

  try {
    const newCh = await channel.clone({ name, topic, parent, permissionOverwrites: overwrites, position: pos });
    await channel.delete('Nuked');
    await newCh.send({ embeds: [successEmbed('Channel Nuked', '💣 Channel has been nuked and recreated.')] });
    await sendLog(ctx.guild, modEmbed('Channel Nuked', ctx.member.user, { tag: name, id: channel.id }, 'Nuke command'), db);
  } catch (e) {
    ctx.reply({ embeds: [errorEmbed('Failed', e.message)] });
  }
});

// ───────────────────────────────────────────────────────────────
//  NICKNAME
// ───────────────────────────────────────────────────────────────
cmd('nickname', ['nick'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved?.member) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that member.')] });

  const newNick = ctx.args.slice(1).join(' ') || null;
  try {
    await resolved.member.setNickname(newNick, `Changed by ${ctx.member.user.tag}`);
    ctx.reply({ embeds: [successEmbed('Nickname Changed', `${resolved.user}'s nickname set to: **${newNick || '(reset)'}**`)] });
  } catch (e) {
    ctx.reply({ embeds: [errorEmbed('Failed', e.message)] });
  }
});

// ───────────────────────────────────────────────────────────────
//  ROLE
// ───────────────────────────────────────────────────────────────
cmd('role', [], async (ctx) => {
  if (!hasAdminPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Guild permission.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved?.member) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that member.')] });

  const roleInput = ctx.args[1];
  if (!roleInput) return ctx.reply({ embeds: [errorEmbed('Missing Role', 'Provide a role mention or ID.')] });

  const roleId = roleInput.replace(/[<@&>]/g, '');
  const role = ctx.guild.roles.cache.get(roleId);
  if (!role) return ctx.reply({ embeds: [errorEmbed('Role Not Found', 'Could not find that role.')] });

  const { member } = resolved;
  try {
    if (member.roles.cache.has(role.id)) {
      await member.roles.remove(role);
      ctx.reply({ embeds: [successEmbed('Role Removed', `Removed ${role} from ${member.user.tag}.`)] });
    } else {
      await member.roles.add(role);
      ctx.reply({ embeds: [successEmbed('Role Added', `Added ${role} to ${member.user.tag}.`)] });
    }
  } catch (e) {
    ctx.reply({ embeds: [errorEmbed('Failed', e.message)] });
  }
});

// ───────────────────────────────────────────────────────────────
//  PURGE
// ───────────────────────────────────────────────────────────────
cmd('purge', ['clear', 'prune'], async (ctx) => {
  if (!ctx.member.permissions.has(PermissionFlagsBits.ManageMessages)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Messages permission.')] });

  const amount = parseInt(ctx.args[0]);
  if (!amount || amount < 1 || amount > 100) return ctx.reply({ embeds: [errorEmbed('Invalid Amount', 'Provide a number between 1 and 100.')] });

  try {
    const deleted = await ctx.channel.bulkDelete(amount, true);
    const msg = await ctx.channel.send({ embeds: [successEmbed('Purge Complete', `Deleted **${deleted.size}** messages.`)] });
    setTimeout(() => msg.delete().catch(() => null), 4000);
  } catch (e) {
    ctx.reply({ embeds: [errorEmbed('Failed', e.message)] });
  }
});

// ───────────────────────────────────────────────────────────────
//  SLOWMODE
// ───────────────────────────────────────────────────────────────
cmd('slowmode', ['slow'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const seconds = parseInt(ctx.args[0]);
  if (isNaN(seconds) || seconds < 0 || seconds > 21600) return ctx.reply({ embeds: [errorEmbed('Invalid', 'Slowmode must be 0–21600 seconds.')] });

  try {
    await ctx.channel.setRateLimitPerUser(seconds);
    ctx.reply({ embeds: [successEmbed('Slowmode Set', seconds === 0 ? 'Slowmode disabled.' : `Slowmode set to **${seconds}s**.`)] });
  } catch (e) {
    ctx.reply({ embeds: [errorEmbed('Failed', e.message)] });
  }
});

// ───────────────────────────────────────────────────────────────
//  FILTER
// ───────────────────────────────────────────────────────────────
cmd('filter', [], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const sub = ctx.args[0]?.toLowerCase();
  const word = ctx.args[1]?.toLowerCase();

  if (sub === 'add') {
    if (!word) return ctx.reply({ embeds: [errorEmbed('Missing Word', 'Provide a word to filter.')] });
    const added = db.addFilterWord(ctx.guild.id, word);
    return ctx.reply({ embeds: [added ? successEmbed('Word Added', `\`${word}\` added to filter.`) : infoEmbed('Already Filtered', `\`${word}\` is already in the filter.`)] });
  }

  if (sub === 'remove' || sub === 'del') {
    if (!word) return ctx.reply({ embeds: [errorEmbed('Missing Word', 'Provide a word to remove.')] });
    const removed = db.removeFilterWord(ctx.guild.id, word);
    return ctx.reply({ embeds: [removed ? successEmbed('Word Removed', `\`${word}\` removed from filter.`) : errorEmbed('Not Found', `\`${word}\` is not in the filter.`)] });
  }

  if (sub === 'list' || !sub) {
    const words = db.getFilterWords(ctx.guild.id);
    return ctx.reply({ embeds: [infoEmbed('Filter List', words.length ? `\`${words.join('`, `')}\`` : 'No filtered words.')] });
  }

  ctx.reply({ embeds: [errorEmbed('Invalid Subcommand', 'Use: `filter add <word>`, `filter remove <word>`, or `filter list`')] });
});

// ───────────────────────────────────────────────────────────────
//  AVATAR
// ───────────────────────────────────────────────────────────────
cmd('avatar', ['av', 'pfp'], async (ctx) => {
  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0] || ctx.member.id);
  const user = resolved?.user || ctx.member.user;

  const embed = new EmbedBuilder()
    .setColor(0x5865F2)
    .setTitle(`🖼️ ${user.tag}'s Avatar`)
    .setImage(user.displayAvatarURL({ dynamic: true, size: 1024 }))
    .setDescription(`[PNG](${user.displayAvatarURL({ format: 'png', size: 1024 })}) | [WebP](${user.displayAvatarURL({ format: 'webp', size: 1024 })}) | [JPG](${user.displayAvatarURL({ format: 'jpg', size: 1024 })})`)
    .setTimestamp();

  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  LOGSCHANNEL
// ───────────────────────────────────────────────────────────────
cmd('logschannel', ['setlogs', 'logs'], async (ctx) => {
  if (!hasAdminPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need Manage Guild permission.')] });

  const channelInput = ctx.args[0];
  if (!channelInput) return ctx.reply({ embeds: [errorEmbed('Missing Channel', 'Mention or provide a channel ID.')] });

  const channelId = channelInput.replace(/[<#>]/g, '');
  const channel = ctx.guild.channels.cache.get(channelId);
  if (!channel) return ctx.reply({ embeds: [errorEmbed('Channel Not Found', 'Could not find that channel.')] });

  db.setConfig(ctx.guild.id, 'logsChannelId', channel.id);
  ctx.reply({ embeds: [successEmbed('Logs Channel Set', `All mod logs will be sent to ${channel}.`)] });
});

// ───────────────────────────────────────────────────────────────
//  SERVERINFO
// ───────────────────────────────────────────────────────────────
cmd('serverinfo', ['si', 'server'], async (ctx) => {
  const guild = ctx.guild;
  await guild.fetch();

  const embed = new EmbedBuilder()
    .setColor(0x5865F2)
    .setTitle(`📊 ${guild.name}`)
    .setThumbnail(guild.iconURL({ dynamic: true }))
    .addFields(
      { name: '👑 Owner', value: `<@${guild.ownerId}>`, inline: true },
      { name: '📅 Created', value: `<t:${Math.floor(guild.createdTimestamp / 1000)}:R>`, inline: true },
      { name: '👥 Members', value: `${guild.memberCount}`, inline: true },
      { name: '💬 Channels', value: `${guild.channels.cache.size}`, inline: true },
      { name: '🎭 Roles', value: `${guild.roles.cache.size}`, inline: true },
      { name: '🌍 Region', value: guild.preferredLocale || 'Unknown', inline: true },
      { name: '🔒 Verification', value: guild.verificationLevel.toString(), inline: true },
      { name: '🆔 Server ID', value: guild.id, inline: true }
    )
    .setTimestamp();

  if (guild.description) embed.setDescription(guild.description);
  if (guild.bannerURL()) embed.setImage(guild.bannerURL({ size: 1024 }));

  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  CHATBAN REVIEW PANEL
// ───────────────────────────────────────────────────────────────
cmd('reviewpanel', ['cbpanel', 'cbr'], async (ctx) => {
  if (!hasModPermission(ctx.member)) return ctx.reply({ embeds: [errorEmbed('No Permission', 'You need moderation permissions.')] });

  const resolved = await resolveUser(ctx.client, ctx.guild, ctx.args[0]);
  if (!resolved) return ctx.reply({ embeds: [errorEmbed('User Not Found', 'Could not find that user.')] });

  const { user } = resolved;
  const chatbanData = db.getChatban(ctx.guild.id, user.id);
  const warnings = db.getWarnings(ctx.guild.id, user.id);

  const embed = new EmbedBuilder()
    .setColor(0xEB459E)
    .setTitle('🔍 Chatban Review Panel')
    .setThumbnail(user.displayAvatarURL())
    .addFields(
      { name: 'User', value: `${user.tag} (\`${user.id}\`)` },
      { name: 'Status', value: chatbanData ? '🔴 Currently Chatbanned' : '🟢 Not Chatbanned', inline: true },
      { name: 'Warnings', value: `${warnings.length}`, inline: true },
      { name: 'Chatban Reason', value: chatbanData?.reason || 'N/A', inline: false },
      { name: 'Applied', value: chatbanData ? `<t:${Math.floor(new Date(chatbanData.appliedAt).getTime() / 1000)}:R>` : 'N/A', inline: true },
      { name: 'Expires', value: chatbanData?.expiresAt ? `<t:${Math.floor(new Date(chatbanData.expiresAt).getTime() / 1000)}:R>` : 'Permanent', inline: true }
    )
    .setTimestamp();

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`cbr_increase_${user.id}`).setLabel('⬆ Increase Ban').setStyle(ButtonStyle.Danger),
    new ButtonBuilder().setCustomId(`cbr_decrease_${user.id}`).setLabel('⬇ Decrease Ban').setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId(`cbr_remove_${user.id}`).setLabel('🔓 Remove Ban').setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId(`cbr_keep_${user.id}`).setLabel('✅ Keep As-Is').setStyle(ButtonStyle.Secondary)
  );

  ctx.reply({ embeds: [embed], components: [row] });
});

// ───────────────────────────────────────────────────────────────
//  HELP
// ───────────────────────────────────────────────────────────────
cmd('help', ['h', 'commands'], async (ctx) => {
  const embed = new EmbedBuilder()
    .setColor(0x5865F2)
    .setTitle('📚 Moderation Bot Commands')
    .setDescription('Prefix: `.` or `?` — All commands also available as `/command`')
    .addFields(
      {
        name: '⚠️ Warnings',
        value: '`warn <user> [reason]` • `warnings <user>` • `delwarn <user> <id>`'
      },
      {
        name: '🔇 Chat Restrictions',
        value: '`chatban <user> [reason]` • `unchatban <user>`\n`mute <user> <duration> [reason]` • `unmute <user>`'
      },
      {
        name: '🔨 Moderation',
        value: '`kick <user> [reason]` • `ban <user> [reason]` • `unban <id> [reason]`'
      },
      {
        name: '🔍 Information',
        value: '`usercheck <user>` • `avatar [user]` • `serverinfo`\n`note <user> <text>` • `notes <user>` • `delnote <user> <id>`'
      },
      {
        name: '📢 Channel Management',
        value: '`lock` • `unlock` • `lockdown` • `unlockall` • `nuke`\n`slowmode <seconds>` • `purge <amount>`'
      },
      {
        name: '🛡️ User Management',
        value: '`nickname <user> [name]` • `role <user> <role>`'
      },
      {
        name: '🚫 Filter',
        value: '`filter add <word>` • `filter remove <word>` • `filter list`'
      },
      {
        name: '⚙️ Config',
        value: '`logschannel <#channel>` • `reviewpanel <user>`'
      }
    )
    .setFooter({ text: 'Duration format: 10m, 1h, 2d, 1w' })
    .setTimestamp();

  ctx.reply({ embeds: [embed] });
});

// ───────────────────────────────────────────────────────────────
//  DURATION PARSER
// ───────────────────────────────────────────────────────────────
function parseDuration(str) {
  const match = str.match(/^(\d+)(s|m|h|d|w)$/);
  if (!match) return null;
  const num = parseInt(match[1]);
  const unit = match[2];
  const multipliers = { s: 1000, m: 60000, h: 3600000, d: 86400000, w: 604800000 };
  const ms = num * multipliers[unit];
  if (ms > 28 * 24 * 60 * 60 * 1000) return null; // Discord max timeout = 28d
  return ms;
}

module.exports = { commands };


