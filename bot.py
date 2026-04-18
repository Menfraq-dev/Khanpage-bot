import os
import json
import asyncio
import threading
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

# =========================
# FLASK KEEPALIVE PRO RENDER
# =========================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!", 200

@app.route("/healthz")
def healthz():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ===== SERVER =====
GUILD_ID = 1495083809828503642

# ===== HLAVNÍ ROLE PRO VĚTŠINU COMMANDŮ =====
ALLOWED_COMMAND_ROLE_ID = 1495083809840959818

# ===== SPECIÁLNÍ ROLE PRO VYBRANÉ COMMANDY =====
SPECIAL_COMMAND_ROLE_ID = 1495083809840959811

# ===== KANÁLY =====
WELCOME_CHANNEL_ID = 1495083810352795792
RULES_CHANNEL_ID = 1495083810570895461
LOG_CHANNEL_ID = 1495083811149709437
PUNISH_LOG_CHANNEL_ID = 1495083811149709435
REVERT_LOG_CHANNEL_ID = 1495083811149709436
STRIKE_CHANNEL_ID = 1495083810847457539
APP_INFO_CHANNEL_ID = 1495083810570895463
LA_TERRAZA_TEXT_CHANNEL_ID = 1495083810570895462
ROLES_TEXT_CHANNEL_ID = 1495083810352795798

# ===== MESSAGE LOG CHANNEL =====
MESSAGE_LOG_CHANNEL_ID = 1495083811149709438

# ===== AUTO ROLE =====
AUTO_ROLE_IDS = [
    1495083809828503647,
    1495083809828503646,
    1495083809828503645,
]

# ===== OBRÁZEK =====
THUMBNAIL_PATH = "kkangpae_logo.png"

# ===== STRIKES =====
STRIKES_FILE = "strikes.json"
MAX_STRIKES = 3

# ===== INTENTS =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)
guild_obj = discord.Object(id=GUILD_ID)

# pro omezení duplicitních logů
recent_kicks = set()
recent_timeout_updates = {}


# =========================
# STRIKE STORAGE
# =========================
def load_strikes():
    if not os.path.exists(STRIKES_FILE):
        return {}
    try:
        with open(STRIKES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        fixed = {}
        for user_id, value in data.items():
            if isinstance(value, int):
                fixed[user_id] = {
                    "count": value,
                    "message_ids": []
                }
            elif isinstance(value, dict):
                fixed[user_id] = {
                    "count": value.get("count", 0),
                    "message_ids": value.get("message_ids", [])
                }

        return fixed
    except Exception:
        return {}


def save_strikes(data):
    with open(STRIKES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


strikes_data = load_strikes()


# =========================
# POMOCNÉ FUNKCE
# =========================
def format_created(dt):
    return dt.strftime("%d %b %Y")


def chunk_text(text: str, limit: int = 1000) -> str:
    if not text:
        return "*No text content*"
    return text if len(text) <= limit else text[:limit] + "..."


def has_allowed_role(member: discord.Member) -> bool:
    return any(role.id == ALLOWED_COMMAND_ROLE_ID for role in member.roles)


def has_special_role(member: discord.Member) -> bool:
    return any(role.id == SPECIAL_COMMAND_ROLE_ID for role in member.roles)


def build_message_content(message: discord.Message) -> str:
    parts = []

    if message.content:
        parts.append(message.content)

    if message.attachments:
        parts.extend([f"Attachment: {attachment.url}" for attachment in message.attachments])

    if not parts:
        return "*No text content*"

    return chunk_text("\n".join(parts), 1000)


def build_edit_content(before: discord.Message, after: discord.Message) -> tuple[str, str]:
    before_parts = []
    after_parts = []

    if before.content:
        before_parts.append(before.content)
    if after.content:
        after_parts.append(after.content)

    if before.attachments:
        before_parts.extend([f"Attachment: {a.url}" for a in before.attachments])
    if after.attachments:
        after_parts.extend([f"Attachment: {a.url}" for a in after.attachments])

    before_text = "*No text content*" if not before_parts else chunk_text("\n".join(before_parts), 1000)
    after_text = "*No text content*" if not after_parts else chunk_text("\n".join(after_parts), 1000)

    return before_text, after_text


def format_account_age(created_at) -> str:
    now = discord.utils.utcnow()
    delta = now - created_at

    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def is_new_account(created_at, max_days: int = 7) -> bool:
    now = discord.utils.utcnow()
    delta = now - created_at
    return delta.days < max_days


def format_timeout_end(dt):
    if not dt:
        return "None"
    return discord.utils.format_dt(dt, style="f")


async def check_command_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Tento command lze použít jen na serveru.", ephemeral=True)
        return False

    if not has_allowed_role(interaction.user):
        await interaction.response.send_message("❌ Nemáš oprávnění na tento command.", ephemeral=True)
        return False

    return True


async def check_special_command_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Tento command lze použít jen na serveru.", ephemeral=True)
        return False

    if not has_special_role(interaction.user):
        await interaction.response.send_message("❌ Nemáš oprávnění na tento command.", ephemeral=True)
        return False

    return True


async def send_embed_log(
    channel_id: int,
    guild: discord.Guild,
    main_text: str,
    moderator_text: str,
    thumbnail_user: discord.abc.User | None = None,
):
    channel = guild.get_channel(channel_id)
    if not channel:
        print(f"❌ Log kanál {channel_id} nebyl nalezen.")
        return

    embed = discord.Embed(
        description=main_text,
        color=discord.Color.orange()
    )

    embed.set_author(
        name="Logy discordu",
        icon_url=guild.icon.url if guild.icon else None
    )

    if thumbnail_user:
        embed.set_thumbnail(url=thumbnail_user.display_avatar.url)
    elif guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="Responsible Moderator:",
        value=moderator_text,
        inline=False
    )

    embed.add_field(
        name="Time:",
        value=discord.utils.format_dt(discord.utils.utcnow(), style="f"),
        inline=False
    )

    await channel.send(embed=embed)


async def send_message_log(
    guild: discord.Guild,
    description_lines: list[str],
    thumbnail_user: discord.abc.User | None = None,
):
    channel = guild.get_channel(MESSAGE_LOG_CHANNEL_ID)
    if not channel:
        print(f"❌ Message log kanál {MESSAGE_LOG_CHANNEL_ID} nebyl nalezen.")
        return

    embed = discord.Embed(
        description="\n".join(description_lines),
        color=discord.Color.red()
    )

    embed.set_author(
        name="Logy discordu",
        icon_url=guild.icon.url if guild.icon else None
    )

    if thumbnail_user:
        embed.set_thumbnail(url=thumbnail_user.display_avatar.url)
    elif guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="Time:",
        value=discord.utils.format_dt(discord.utils.utcnow(), style="f"),
        inline=False
    )

    await channel.send(embed=embed)


async def send_member_log(
    guild: discord.Guild,
    description_lines: list[str],
    thumbnail_user: discord.abc.User | None = None,
    color: discord.Color = discord.Color.green()
):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        print(f"❌ Member log kanál {LOG_CHANNEL_ID} nebyl nalezen.")
        return

    embed = discord.Embed(
        description="\n".join(description_lines),
        color=color
    )

    embed.set_author(
        name="Logy discordu",
        icon_url=guild.icon.url if guild.icon else None
    )

    if thumbnail_user:
        embed.set_thumbnail(url=thumbnail_user.display_avatar.url)
    elif guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="Time:",
        value=discord.utils.format_dt(discord.utils.utcnow(), style="f"),
        inline=False
    )

    await channel.send(embed=embed)


async def send_mod_audit_log(
    channel_id: int,
    guild: discord.Guild,
    description_lines: list[str],
    color: discord.Color,
    thumbnail_user: discord.abc.User | None = None,
):
    channel = guild.get_channel(channel_id)
    if not channel:
        print(f"❌ Mod log kanál {channel_id} nebyl nalezen.")
        return

    embed = discord.Embed(
        description="\n".join(description_lines),
        color=color
    )

    embed.set_author(
        name="Logy discordu",
        icon_url=guild.icon.url if guild.icon else None
    )

    if thumbnail_user:
        embed.set_thumbnail(url=thumbnail_user.display_avatar.url)
    elif guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="Time:",
        value=discord.utils.format_dt(discord.utils.utcnow(), style="f"),
        inline=False
    )

    await channel.send(embed=embed)


async def get_delete_action_by_cached(message: discord.Message) -> str:
    if not message.guild:
        return "Author / System / Unknown"

    try:
        await asyncio.sleep(1)

        async for entry in message.guild.audit_logs(limit=8, action=discord.AuditLogAction.message_delete):
            if not entry.target:
                continue

            target_id = getattr(entry.target, "id", None)
            if target_id != message.author.id:
                continue

            extra_channel = getattr(entry.extra, "channel", None)
            if extra_channel and extra_channel.id != message.channel.id:
                continue

            entry_age = (discord.utils.utcnow() - entry.created_at).total_seconds()
            if entry_age > 10:
                continue

            if entry.user:
                return entry.user.mention

        return "Author / System / Unknown"
    except discord.Forbidden:
        return "Author / System / Unknown"
    except Exception as e:
        print(f"❌ Chyba při čtení audit logu: {e}")
        return "Author / System / Unknown"


async def get_delete_action_by_raw(guild: discord.Guild, channel_id: int) -> str:
    try:
        await asyncio.sleep(1)

        async for entry in guild.audit_logs(limit=8, action=discord.AuditLogAction.message_delete):
            entry_age = (discord.utils.utcnow() - entry.created_at).total_seconds()
            if entry_age > 10:
                continue

            extra_channel = getattr(entry.extra, "channel", None)
            if extra_channel and extra_channel.id != channel_id:
                continue

            if entry.user:
                return entry.user.mention

        return "Unknown / Not Cached"
    except discord.Forbidden:
        return "Unknown / Not Cached"
    except Exception as e:
        print(f"❌ Chyba při čtení audit logu: {e}")
        return "Unknown / Not Cached"


async def get_recent_audit_entry(guild: discord.Guild, action: discord.AuditLogAction, target_id: int, max_age: int = 12):
    try:
        await asyncio.sleep(1)
        async for entry in guild.audit_logs(limit=10, action=action):
            entry_target_id = getattr(entry.target, "id", None)
            if entry_target_id != target_id:
                continue

            entry_age = (discord.utils.utcnow() - entry.created_at).total_seconds()
            if entry_age > max_age:
                continue

            return entry
    except discord.Forbidden:
        return None
    except Exception as e:
        print(f"❌ Chyba při čtení audit logu: {e}")
        return None
    return None


async def send_strike_message(
    guild: discord.Guild,
    member: discord.Member,
    strike_number: int,
    reason: str
):
    channel = guild.get_channel(STRIKE_CHANNEL_ID)
    if not channel:
        print("❌ Strike kanál nebyl nalezen.")
        return None

    embed = discord.Embed(
        description=(
            f"⚠️ {member.mention} obdržel **Strike #{strike_number}**.\n\n"
            f"**Důvod:** {reason}"
        ),
        color=discord.Color.red()
    )

    embed.set_author(
        name=str(member),
        icon_url=member.display_avatar.url
    )

    msg = await channel.send(embed=embed)
    return msg.id


# =========================
# READY
# =========================
@bot.event
async def on_ready():
    print(f"✅ Bot je online jako {bot.user}")
    try:
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"✅ Slash commandy synchronizovány: {len(synced)}")
    except Exception as e:
        print(f"❌ Chyba při sync slash commandů: {e}")


# =========================
# JOIN
# =========================
@bot.event
async def on_member_join(member):
    print(f"👤 Nový člen: {member}")

    for role_id in AUTO_ROLE_IDS:
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Automatické role po příchodu na server")

                await send_embed_log(
                    channel_id=LOG_CHANNEL_ID,
                    guild=member.guild,
                    main_text=f"🏷️ **Role Added:** {role.mention}\n👤 **User:** {member.mention}",
                    moderator_text="System",
                    thumbnail_user=member
                )
            except discord.Forbidden:
                print(f"❌ Bot nemá oprávnění přidělit roli {role.name}")
            except Exception as e:
                print(f"❌ Chyba při přidávání role {role.name}: {e}")

    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        rules_mention = f"<#{RULES_CHANNEL_ID}>"
        created_at = format_created(member.created_at)

        embed = discord.Embed(
            description=(
                f"• Dorazil {member.mention}\n"
                f"• Nezapomeň si přečíst {rules_mention}\n"
                f"📅 Account created: {created_at}"
            ),
            color=discord.Color.orange()
        )

        embed.set_author(
            name=str(member),
            icon_url=member.display_avatar.url
        )

        if os.path.exists(THUMBNAIL_PATH):
            file = discord.File(THUMBNAIL_PATH, filename="kkangpae_logo.png")
            embed.set_thumbnail(url="attachment://kkangpae_logo.png")
            await channel.send(embed=embed, file=file)
        else:
            await channel.send(embed=embed)

    join_lines = [
        "✅ **Member Joined**",
        f"👤 **User:** {member.mention}",
        f"🆔 **User ID:** `{member.id}`",
        f"📅 **Account Created:** {discord.utils.format_dt(member.created_at, style='f')}",
        f"⏳ **Account Age:** {format_account_age(member.created_at)}",
        f"📥 **Joined Server:** {discord.utils.format_dt(discord.utils.utcnow(), style='f')}",
    ]

    if is_new_account(member.created_at):
        join_lines.append("⚠️ **New Account:** Yes (< 7 days old)")

    await send_member_log(
        guild=member.guild,
        description_lines=join_lines,
        thumbnail_user=member,
        color=discord.Color.green()
    )


# =========================
# LEAVE / KICK
# =========================
@bot.event
async def on_member_remove(member):
    kick_entry = await get_recent_audit_entry(member.guild, discord.AuditLogAction.kick, member.id)

    if kick_entry:
        recent_kicks.add(member.id)

        reason = kick_entry.reason if kick_entry.reason else "No reason provided"
        moderator = kick_entry.user.mention if kick_entry.user else "Unknown"

        await send_mod_audit_log(
            channel_id=PUNISH_LOG_CHANNEL_ID,
            guild=member.guild,
            description_lines=[
                "👢 **Kick**",
                f"👤 **User:** {member.mention}",
                f"🆔 **User ID:** `{member.id}`",
                f"🛠️ **Action By:** {moderator}",
                f"📄 **Reason:** {reason}",
            ],
            color=discord.Color.red(),
            thumbnail_user=member
        )

        async def clear_recent_kick(user_id: int):
            await asyncio.sleep(15)
            recent_kicks.discard(user_id)

        bot.loop.create_task(clear_recent_kick(member.id))
        return

    leave_lines = [
        "🚪 **Member Left**",
        f"👤 **User:** {member.mention}",
        f"🆔 **User ID:** `{member.id}`",
        f"📅 **Account Created:** {discord.utils.format_dt(member.created_at, style='f')}",
        f"⏳ **Account Age:** {format_account_age(member.created_at)}",
        f"📤 **Left Server:** {discord.utils.format_dt(discord.utils.utcnow(), style='f')}",
    ]

    await send_member_log(
        guild=member.guild,
        description_lines=leave_lines,
        thumbnail_user=member,
        color=discord.Color.red()
    )


# =========================
# BAN
# =========================
@bot.event
async def on_member_ban(guild, user):
    entry = await get_recent_audit_entry(guild, discord.AuditLogAction.ban, user.id)

    moderator = entry.user.mention if entry and entry.user else "Unknown"
    reason = entry.reason if entry and entry.reason else "No reason provided"

    await send_mod_audit_log(
        channel_id=PUNISH_LOG_CHANNEL_ID,
        guild=guild,
        description_lines=[
            "🔨 **Ban**",
            f"👤 **User:** {user.mention}",
            f"🆔 **User ID:** `{user.id}`",
            f"🛠️ **Action By:** {moderator}",
            f"📄 **Reason:** {reason}",
        ],
        color=discord.Color.red(),
        thumbnail_user=user
    )


# =========================
# UNBAN
# =========================
@bot.event
async def on_member_unban(guild, user):
    entry = await get_recent_audit_entry(guild, discord.AuditLogAction.unban, user.id)

    moderator = entry.user.mention if entry and entry.user else "Unknown"
    reason = entry.reason if entry and entry.reason else "No reason provided"

    await send_mod_audit_log(
        channel_id=REVERT_LOG_CHANNEL_ID,
        guild=guild,
        description_lines=[
            "🔓 **Unban**",
            f"👤 **User:** {user.mention}",
            f"🆔 **User ID:** `{user.id}`",
            f"🛠️ **Action By:** {moderator}",
            f"📄 **Reason:** {reason}",
        ],
        color=discord.Color.green(),
        thumbnail_user=user
    )


# =========================
# TIMEOUT / UNTIMEOUT
# =========================
@bot.event
async def on_member_update(before, after):
    if before.bot:
        return

    before_timeout = before.timed_out_until
    after_timeout = after.timed_out_until

    if before_timeout == after_timeout:
        return

    entry = await get_recent_audit_entry(after.guild, discord.AuditLogAction.member_update, after.id)
    if not entry:
        return

    moderator = entry.user.mention if entry.user else "Unknown"
    reason = entry.reason if entry.reason else "No reason provided"

    state_key = (after.guild.id, after.id, str(after_timeout))
    if recent_timeout_updates.get(state_key):
        return
    recent_timeout_updates[state_key] = True

    async def clear_recent_timeout(key):
        await asyncio.sleep(15)
        recent_timeout_updates.pop(key, None)

    bot.loop.create_task(clear_recent_timeout(state_key))

    if after_timeout is not None and (before_timeout is None or after_timeout != before_timeout):
        await send_mod_audit_log(
            channel_id=PUNISH_LOG_CHANNEL_ID,
            guild=after.guild,
            description_lines=[
                "⏳ **Timeout**",
                f"👤 **User:** {after.mention}",
                f"🆔 **User ID:** `{after.id}`",
                f"🛠️ **Action By:** {moderator}",
                f"📅 **Ends:** {format_timeout_end(after_timeout)}",
                f"📄 **Reason:** {reason}",
            ],
            color=discord.Color.red(),
            thumbnail_user=after
        )
        return

    if before_timeout is not None and after_timeout is None:
        await send_mod_audit_log(
            channel_id=REVERT_LOG_CHANNEL_ID,
            guild=after.guild,
            description_lines=[
                "✅ **Timeout Removed**",
                f"👤 **User:** {after.mention}",
                f"🆔 **User ID:** `{after.id}`",
                f"🛠️ **Action By:** {moderator}",
                f"📄 **Reason:** {reason}",
            ],
            color=discord.Color.green(),
            thumbnail_user=after
        )


# =========================
# DELETED MESSAGE
# =========================
@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    channel = guild.get_channel(payload.channel_id)
    cached_message = payload.cached_message

    if cached_message and not cached_message.author.bot:
        action_by = await get_delete_action_by_cached(cached_message)

        await send_message_log(
            guild=guild,
            description_lines=[
                "🗑️ **Deleted Message**",
                f"👤 **User:** {cached_message.author.mention}",
                f"🛠️ **Action By:** {action_by}",
                f"📍 **Channel:** {channel.mention if channel else f'`{payload.channel_id}`'}",
                f"💬 **Message:** {build_message_content(cached_message)}",
            ],
            thumbnail_user=cached_message.author
        )
        return

    action_by = await get_delete_action_by_raw(guild, payload.channel_id)

    await send_message_log(
        guild=guild,
        description_lines=[
            "🗑️ **Deleted Message**",
            f"👤 **User:** `Unknown / Not Cached`",
            f"🛠️ **Action By:** {action_by}",
            f"📍 **Channel:** {channel.mention if channel else f'`{payload.channel_id}`'}",
            f"💬 **Message:** `Unavailable (message was not in cache)`",
        ],
        thumbnail_user=None
    )


# =========================
# EDITED MESSAGE
# =========================
@bot.event
async def on_message_edit(before, after):
    if before.author.bot:
        return
    if not before.guild:
        return
    if before.content == after.content and before.attachments == after.attachments:
        return

    before_text, after_text = build_edit_content(before, after)

    await send_message_log(
        guild=before.guild,
        description_lines=[
            "✏️ **Edited Message**",
            f"👤 **User:** {before.author.mention}",
            f"🛠️ **Action By:** {before.author.mention}",
            f"📍 **Channel:** {before.channel.mention}",
            f"📝 **Before:** {before_text}",
            f"💬 **After:** {after_text}",
        ],
        thumbnail_user=before.author
    )


# =========================
# BASIC COMMANDS
# =========================
@bot.tree.command(name="ping", description="Otestuje bota.", guild=guild_obj)
async def ping(interaction: discord.Interaction):
    if not await check_command_role(interaction):
        return
    await interaction.response.send_message("🏓 Pong!", ephemeral=True)


@bot.tree.command(name="testwelcome", description="Pošle test welcome zprávu.", guild=guild_obj)
async def testwelcome(interaction: discord.Interaction):
    if not await check_command_role(interaction):
        return

    rules_mention = f"<#{RULES_CHANNEL_ID}>"
    created_at = format_created(interaction.user.created_at)

    embed = discord.Embed(
        description=(
            f"• Dorazil {interaction.user.mention}\n"
            f"• Nezapomeň si přečíst {rules_mention}\n"
            f"📅 Account created: {created_at}"
        ),
        color=discord.Color.orange()
    )

    embed.set_author(
        name=str(interaction.user),
        icon_url=interaction.user.display_avatar.url
    )

    if os.path.exists(THUMBNAIL_PATH):
        file = discord.File(THUMBNAIL_PATH, filename="kkangpae_logo.png")
        embed.set_thumbnail(url="attachment://kkangpae_logo.png")
        await interaction.response.send_message(embed=embed, file=file)
    else:
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="sendtext", description="Pošle normální zprávu do vybraného kanálu.", guild=guild_obj)
@app_commands.describe(channel="Vyber kanál", message="Napiš zprávu")
async def sendtext_slash(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if not await check_special_command_role(interaction):
        return

    try:
        await channel.send(message)

        await send_message_log(
            guild=interaction.guild,
            description_lines=[
                "📨 **Text Message Sent**",
                f"🛠️ **Action By:** {interaction.user.mention}",
                f"📍 **Channel:** {channel.mention}",
                f"💬 **Message:** {chunk_text(message)}",
            ],
            thumbnail_user=interaction.user
        )

        await interaction.response.send_message(f"✅ Zpráva byla odeslána do {channel.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Nemám oprávnění psát do tohoto kanálu.", ephemeral=True)


@bot.tree.command(name="sendkkangpae", description="Pošle KKANGPAE lore do určeného kanálu.", guild=guild_obj)
async def sendkkangpae_slash(interaction: discord.Interaction):
    if not await check_command_role(interaction):
        return

    channel = interaction.guild.get_channel(LA_TERRAZA_TEXT_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Cílový kanál nebyl nalezen.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    part1 = (
        "**KKANGPAE**\n\n"
        "KKANGPAE je označení pro staré korejské pouliční gangy a organizovaný zločin, který vznikal v temných částech Soulu, Busanu a Incheonu. "
        "Už od 80. a 90. let si tahle jména lidé spojovali s brutalitou, disciplínou a naprostou loajalitou ke své rodině.\n\n"
        "Na první pohled působili jako obyčejní podnikatelé, majitelé barů, heren nebo nočních klubů. "
        "Ve skutečnosti ale stáli za výpalným, nelegálním hazardem, ochranou podniků, pašováním a tichým odstraňováním problémů.\n\n"
        "KKANGPAE nikdy nebyli o zbytečném hluku. "
        "Nešlo jim o to být vidět. "
        "Šlo jim o to, aby je každý respektoval, i když o nich skoro nikdo nemluvil.\n\n"
        "Po letech konfliktů v Koreji, policejních zásahů a rozpadu starých struktur se část lidí z organizace rozhodla zmizet. "
        "Ne utéct. Rozšířit vliv.\n\n"
        "Několik vybraných členů bylo posláno do Los Santos, kde se rychle ukázalo, že město je plné chaosu, slabých aliancí a příležitostí."
    )

    part2 = (
        "V Los Santos začali nenápadně.\n\n"
        "Přes noční podniky, bary, soukromé herny, dovoz luxusního zboží a ochranu vybraných lidí si začali budovat jméno. "
        "Venku působí klidně, stylově a organizovaně. Uvnitř ale fungují podle starých pravidel:\n\n"
        "• loajalita nade vše\n"
        "• zrada se netoleruje\n"
        "• rodina je víc než peníze\n"
        "• respekt se nevyžaduje, respekt se bere\n\n"
        "Na ulici nejsou nejhlasitější.\n"
        "Nepotřebují křičet, aby je město slyšelo.\n"
        "Když se objeví problém, KKANGPAE ho vyřeší rychle, čistě a bez zbytečných otázek."
    )

    part3 = (
        "Dnes je KKANGPAE v Los Santos známé jméno mezi lidmi, kteří vědí, kam se dívat.\n\n"
        "Nejsou to jen gangsteři z ulice.\n"
        "Jsou to organizace s tradicí, kodexem a tváří, za kterou se skrývá násilí, obchod a absolutní kontrola."
    )

    try:
        await channel.send(part1)
        await channel.send(part2)
        await channel.send(part3)

        await send_embed_log(
            channel_id=LOG_CHANNEL_ID,
            guild=interaction.guild,
            main_text=(
                f"📨 **KKANGPAE Lore Sent**\n"
                f"📍 **Channel:** {channel.mention}"
            ),
            moderator_text=interaction.user.mention,
            thumbnail_user=interaction.user
        )

        await interaction.followup.send("✅ KKANGPAE lore bylo odesláno.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ Nemám oprávnění psát do tohoto kanálu.", ephemeral=True)


@bot.tree.command(name="sendruleslt", description="Pošle pravidla do rules kanálu.", guild=guild_obj)
async def sendruleslt_slash(interaction: discord.Interaction):
    if not await check_command_role(interaction):
        return

    channel = interaction.guild.get_channel(RULES_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Cílový kanál nebyl nalezen.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    part1 = (
        "**TYTO PRAVIDLA JSOU BRÁNA JAK IC TAK I OOC**\n\n"
        "Pokud chceš být součástí této nelegální frakce, nesmíš být za jakoukoliv postavu součástí jiné nelegální frakce. (vyber si pouze jednu frakci) To stejné platí na IC.\n\n"
        "Nevynášej informace z DC (pokud se přijde na vynášení infa z toho to DC) budeš nahlášen - AT který ti udělí ban + smaže postavu JELIKOŽ NEJSI PRO NÁS KVALITNÍ RP HRÁČ A **NECHCEME TĚ ZDE !**\n\n"
        "**NETRASHUJ** na nikoho z frakce ani mimo frakci... když se ti něco nelíbí napiš mi to do PM, zakládáme si na kvalitě né kvantitě.\n\n"
        "Nepřenášej OOC do IC a opačně, po porušení budeš nahlášen AT.\n\n"
        "Pokud budeš trashovaný od někoho z jiné frakce, zachovej profesionalitu a neřeš ho, popř... ho reportni, nejde o krysáctví ale o kvalitě celé frakce a serveru. (může se stát že to odneseš i ty sám)\n\n"
        "Nehraji na počty ale na kvalitu... pokud budeš trashovat a vyvolávat hroty tak počítej že i já půjdu proti tobě.\n\n"
        "**Přísný zákaz streamovat lokaci varny** a když do ní jedeš (vždy si přehoď scénu aby nebylo vidět kde to je.) poté předěl streamovat již můžeš.\n\n"
        "**Přísný zákaz sdělovat frekvenci vysílačky či ji streamovat na streamu** (vždy si hoďte něco skrz)\n\n"
        "Každý člen co bude zde na DC bude mít IC nick... žádné \"Los Mistros a podobné sračky... - **TAK JAK TO MÁ VE HŘE BUDE TO MÍT I ZDE !!!**\n\n"
        "Pokud hodláš RPit trash, jako sebevražedné sklony tak radši leavni.\n\n"
        "**RPíme zde kvalitní roleplay – seriozní! Je zakázáno rpit trash!**\n\n"
        "Držíme se svého loru frakce a loru Vaší postavy! (**Porušení loru automaticky schvalujete smazání postavy ATeamem + X měsíční ban.**)"
    )

    part2 = (
        "Řídíte se nařízeními, které dávají nejvyšší! (Při neuposlechnutí se jedná o porušení Loru Frakce)\n\n"
        "**Neděláte nic na vlastní pěst!**\n\n"
        "**Nikdy nerozhoduje jedinec! – vždy se akce odsouhlasí všemi z vedení!**\n\n"
        "Nelegální pravidla nelegálek jsou nastavena tak, že s CK souhlasit nemusíte, ale pokud Vám ho udělí vedení.. neuděláte nic a vaše RPčko skončilo.\n\n"
        "**Na veřejnosti nebudete dělat ostudu frakci!**\n\n"
        "Pokud napojíš, ihned budeš na vysílačce, kde se ohlásíš!\n\n"
        "Okradeš-li frakci, či vlastního člena, to radši zemři.\n\n"
        "Rozhodni se, čemu dáš přednost – této vlastní frakci, nebo trash gangům a mafiím!\n\n"
        "Pokud budeš mít s čímkoliv problém, obrať se vždy na své vedení frakce.\n\n"
        "**JEDEN ZA VŠECHNY, VŠICHNI ZA JEDNOHO - TÁHNEME ZA JEDEN PROVAZ!**\n\n"
        "**Nesnitchuj PD/SD ani nikomu mimo frakci naše informace.**\n\n"
        "Nepovyšuje se nad ostatními, jsi člověk jako ostatní, pokud budeš mít s někým problém přijdeš ho řešit s vedením.\n\n"
        "Pokud nebudeš dodržovat to co máš a to co se ti řekne, popř... začneš pomlouvat někoho z vedení automaticky si v píči.\n\n"
        "**Vždy buď na vysílačce, nikomu nesděluj vysílačku.**\n\n"
        "**Nikdy nemluv na veřejnosti o něčem nelegálním !**"
    )

    part3 = (
        "Neodmlouvej vyšším, když s něčím nebudeš souhlasit, přijdeš za dalším vyšším.\n\n"
        "Pokud se zjistí že máš sebevražedné sklony automaticky si v píči.\n\n"
        "Chovej se všude tak, aby jsi hezky a správně reprezentoval naší organizaci, nechovej se jak totální hajzl, to platí i před PD/SD.\n\n"
        "**NEEXISTUJE** aby tu bylo nějaké nabalování/mazlení mezi sebou, kdo bude chtít s někým něco RPit přijde za BOSS a RIGHT HAND. (pokud to někdo poruší bez nahlášení automaticky dostaneš CK bez slitování.)\n\n"
        "**KDO NEPOTVRDÍ PŘEČTENÍ, AUTOMATICKY SOUHLASÍ I BEZ POTVRZENÍ**\n\n"
        "**!! POTVRĎ PŘEČTENÍ !!**"
    )

    try:
        await channel.send(part1)
        await channel.send(part2)
        await channel.send(part3)

        await send_embed_log(
            channel_id=LOG_CHANNEL_ID,
            guild=interaction.guild,
            main_text=f"📨 **Rules Sent**\n📍 **Channel:** {channel.mention}",
            moderator_text=interaction.user.mention,
            thumbnail_user=interaction.user
        )

        await interaction.followup.send("✅ Pravidla byla odeslána.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ Nemám oprávnění psát do toho kanálu.", ephemeral=True)


@bot.tree.command(name="sendroleslt", description="Pošle seznam hodností do určeného kanálu.", guild=guild_obj)
async def sendroleslt_slash(interaction: discord.Interaction):
    if not await check_command_role(interaction):
        return

    channel = interaction.guild.get_channel(ROLES_TEXT_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Cílový kanál nebyl nalezen.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    message = (
        "**Patron**\n"
        "- Nejvyšší autorita celé organizace. Hlava skupiny, která určuje směr frakce, rozhoduje o zásadních věcech a má poslední slovo při všech důležitých rozhodnutích.\n\n"
        "**Jefe del Jefes**\n"
        "- Pravá ruka Patrona a druhá nejvyšší pozice v hierarchii. Dohlíží na chod celé organizace, koordinuje vyšší vedení a zastupuje Patrona v jeho nepřítomnosti.\n\n"
        "**El Jefe**\n"
        "- Vysoce postavený člen vedení, který dohlíží na plnění rozkazů, organizuje důležité akce a drží pořádek mezi vyšší strukturou frakce.\n\n"
        "**Sub Jefe**\n"
        "- Nižší vedení organizace. Pomáhá s interním chodem frakce, předává informace směrem dolů i nahoru a dohlíží na disciplínu mezi členy.\n\n"
        "**Capitán de capitanes**\n"
        "- Zkušený a respektovaný velitel nižších struktur. Má na starost koordinaci více členů najednou, organizaci menších akcí a udržování pořádku mezi velitelskou úrovní.\n\n"
        "**Captain**\n"
        "- Důležitý člen command struktury, který vede běžné členy v terénu, předává rozkazy od vyšších pozic a dohlíží na správné fungování při každodenních aktivitách frakce.\n\n"
        "**Sub Capo**\n"
        "- Zástupce commandu a opora pro vyšší členy. Pomáhá s organizací lidí, kontroluje aktivitu členů a dbá na to, aby byly rozkazy plněny bez zbytečných chyb.\n\n"
        "**Asociade de honor**\n"
        "- Prověřený a vážený člen organizace, který si vybudoval respekt svou loajalitou a přístupem. Není součástí nejvyššího velení, ale má ve frakci silné postavení a důvěru vedení.\n\n"
        "**Sicario**\n"
        "- Specializovaný člen určený pro citlivé, nebezpečné a důležité úkoly. Je známý svou efektivitou, loajalitou a schopností jednat rychle bez zbytečné pozornosti.\n\n"
        "**Soldado**\n"
        "- Plnohodnotný člen. Základní stavební kámen celé organizace, který se aktivně podílí na chodu frakce, respektuje vedení a reprezentuje jméno skupiny v ulicích."
    )

    try:
        await channel.send(message)

        await send_embed_log(
            channel_id=LOG_CHANNEL_ID,
            guild=interaction.guild,
            main_text=f"📨 **Roles Text Sent**\n📍 **Channel:** {channel.mention}",
            moderator_text=interaction.user.mention,
            thumbnail_user=interaction.user
        )

        await interaction.followup.send("✅ Zpráva byla odeslána.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ Nemám oprávnění psát do toho kanálu.", ephemeral=True)


# =========================
# ROLE COMMANDS
# =========================
@bot.tree.command(name="addrole", description="Přidá roli uživateli.", guild=guild_obj)
@app_commands.describe(user="Vyber uživatele", role="Vyber roli")
async def addrole_slash(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not await check_command_role(interaction):
        return

    try:
        await user.add_roles(role, reason=f"Role added by {interaction.user}")

        await send_embed_log(
            channel_id=LOG_CHANNEL_ID,
            guild=interaction.guild,
            main_text=(
                f"➕ **Role Added Manually**\n"
                f"👤 **User:** {user.mention}\n"
                f"🏷️ **Role:** {role.mention}"
            ),
            moderator_text=interaction.user.mention,
            thumbnail_user=user
        )

        await interaction.response.send_message(f"✅ Role {role.mention} byla přidána uživateli {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Nemám oprávnění přidat tuhle roli.", ephemeral=True)


@bot.tree.command(name="removerole", description="Odebere roli uživateli.", guild=guild_obj)
@app_commands.describe(user="Vyber uživatele", role="Vyber roli")
async def removerole_slash(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not await check_special_command_role(interaction):
        return

    try:
        await user.remove_roles(role, reason=f"Role removed by {interaction.user}")

        await send_embed_log(
            channel_id=LOG_CHANNEL_ID,
            guild=interaction.guild,
            main_text=(
                f"➖ **Role Removed Manually**\n"
                f"👤 **User:** {user.mention}\n"
                f"🏷️ **Role:** {role.mention}"
            ),
            moderator_text=interaction.user.mention,
            thumbnail_user=user
        )

        await interaction.response.send_message(f"✅ Role {role.mention} byla odebrána uživateli {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Nemám oprávnění odebrat tuhle roli.", ephemeral=True)


# =========================
# CHAT COMMAND
# =========================
@bot.tree.command(name="clear", description="Smaže zprávy v aktuálním kanálu bez změny channel ID.", guild=guild_obj)
@app_commands.describe(amount="Počet zpráv ke smazání, napiš 0 pro vyčištění všeho co jde")
async def clear_slash(interaction: discord.Interaction, amount: int = 0):
    if not await check_command_role(interaction):
        return

    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ Tento command funguje jen v textovém kanálu.", ephemeral=True)
        return

    try:
        await interaction.response.send_message("✅ Mažu zprávy...", ephemeral=True)

        deleted = 0

        if amount <= 0:
            while True:
                batch = await channel.purge(limit=100, bulk=True)
                if not batch:
                    break
                deleted += len(batch)
                if len(batch) < 100:
                    break
        else:
            batch = await channel.purge(limit=amount, bulk=True)
            deleted = len(batch)

        await send_message_log(
            guild=interaction.guild,
            description_lines=[
                "🧹 **Channel Cleared**",
                f"🛠️ **Action By:** {interaction.user.mention}",
                f"📍 **Channel:** {channel.mention}",
                f"🗑️ **Deleted Messages:** {deleted}",
            ],
            thumbnail_user=interaction.user
        )

    except discord.Forbidden:
        await interaction.followup.send("❌ Nemám oprávnění mazat zprávy v tomto kanálu.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Chyba při mazání zpráv: {e}", ephemeral=True)


# =========================
# STRIKE COMMANDS
# =========================
@bot.tree.command(name="strike", description="Přidá uživateli strike.", guild=guild_obj)
@app_commands.describe(user="Vyber uživatele", reason="Důvod strike")
async def strike_slash(interaction: discord.Interaction, user: discord.Member, reason: str):
    if not await check_special_command_role(interaction):
        return

    user_id = str(user.id)
    user_data = strikes_data.get(user_id, {"count": 0, "message_ids": []})
    current = user_data.get("count", 0)

    if current >= MAX_STRIKES:
        await interaction.response.send_message(
            f"❌ {user.mention} už má maximum strike ({MAX_STRIKES}).",
            ephemeral=True
        )
        return

    current += 1

    msg_id = await send_strike_message(interaction.guild, user, current, reason)

    user_data["count"] = current
    if msg_id:
        user_data.setdefault("message_ids", []).append(msg_id)

    strikes_data[user_id] = user_data
    save_strikes(strikes_data)

    await send_embed_log(
        channel_id=LOG_CHANNEL_ID,
        guild=interaction.guild,
        main_text=(
            f"⚠️ **Strike Added**\n"
            f"👤 **User:** {user.mention}\n"
            f"🔢 **Strike:** #{current}\n"
            f"📄 **Reason:** {reason}"
        ),
        moderator_text=interaction.user.mention,
        thumbnail_user=user
    )

    await interaction.response.send_message(
        f"✅ {user.mention} dostal Strike #{current}.",
        ephemeral=True
    )


@bot.tree.command(name="removestrike", description="Odebere uživateli 1 strike.", guild=guild_obj)
@app_commands.describe(user="Vyber uživatele")
async def removestrike_slash(interaction: discord.Interaction, user: discord.Member):
    if not await check_special_command_role(interaction):
        return

    user_id = str(user.id)
    user_data = strikes_data.get(user_id, {"count": 0, "message_ids": []})
    current = user_data.get("count", 0)
    message_ids = user_data.get("message_ids", [])

    if current <= 0:
        await interaction.response.send_message(
            f"❌ {user.mention} nemá žádný strike.",
            ephemeral=True
        )
        return

    if message_ids:
        last_message_id = message_ids.pop()

        strike_channel = interaction.guild.get_channel(STRIKE_CHANNEL_ID)
        if strike_channel:
            try:
                msg = await strike_channel.fetch_message(last_message_id)
                await msg.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"❌ Nepodařilo se smazat strike zprávu: {e}")

    current -= 1

    if current == 0:
        strikes_data.pop(user_id, None)
    else:
        user_data["count"] = current
        user_data["message_ids"] = message_ids
        strikes_data[user_id] = user_data

    save_strikes(strikes_data)

    await send_embed_log(
        channel_id=LOG_CHANNEL_ID,
        guild=interaction.guild,
        main_text=(
            f"✅ **Strike Removed**\n"
            f"👤 **User:** {user.mention}\n"
            f"🔢 **Remaining Strikes:** {current}"
        ),
        moderator_text=interaction.user.mention,
        thumbnail_user=user
    )

    await interaction.response.send_message(
        f"✅ {user.mention} byl odebrán 1 strike. Zbývá: {current}.",
        ephemeral=True
    )


@bot.tree.command(name="strikes", description="Ukáže počet strike uživatele.", guild=guild_obj)
@app_commands.describe(user="Vyber uživatele")
async def strikes_slash(interaction: discord.Interaction, user: discord.Member):
    if not await check_special_command_role(interaction):
        return

    user_data = strikes_data.get(str(user.id), {"count": 0, "message_ids": []})
    current = user_data.get("count", 0)

    await interaction.response.send_message(
        f"📌 {user.mention} má aktuálně **{current}/{MAX_STRIKES}** strike.",
        ephemeral=True
    )


# =========================
# APP INFO COMMAND
# =========================
@bot.tree.command(name="sendappinfo", description="Pošle info o aplikaci do určeného kanálu.", guild=guild_obj)
async def sendappinfo_slash(interaction: discord.Interaction):
    if not await check_command_role(interaction):
        return

    channel = interaction.guild.get_channel(APP_INFO_CHANNEL_ID)

    if not channel:
        await interaction.response.send_message("❌ Cílový kanál nebyl nalezen.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Funkčnost této aplikace:",
        description=(
            "**Tato aplikace funguje jako webový prohlížeč pod různými IP adresami viz níže**\n\n"
            "`158.698.789:5890`\n"
            "`178.589.568:3215`\n"
            "`458.654.256:2221`\n\n"
            "**Tyto IP adresy se vždy píšou do anonymního režimu buď v mobilu nebo na zařízeních k tomu určených**\n\n"
            "**Dále se musí uživatel přihlásit pod heslem které se pravidelně mění**\n\n"
            "`546897`\n"
            "`123547`\n"
            "`569874`\n"
            "`123654`\n"
            "`456871`\n"
            "`321987`\n"
            "`456879`\n\n"
            "**Celá aplikace se zálohuje a její konverzace se vždy maže po 24 hodinách, historie je vždy dohledatelná v zálohách na jiném serveru.**"
        ),
        color=discord.Color.orange()
    )

    embed.set_author(
        name="Informace",
        icon_url=interaction.guild.icon.url if interaction.guild.icon else None
    )

    embed.set_footer(text="KKANGPAE")

    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Embed zpráva byla odeslána.", ephemeral=True)


if not TOKEN:
    raise ValueError("❌ Chybí DISCORD_TOKEN v environment variables nebo v .env souboru!")

def start_web():
    try:
        run_web()
    except Exception as e:
        print(f"❌ Flask chyba: {e}")

web_thread = threading.Thread(target=start_web, daemon=True)
web_thread.start()

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Discord bot crash: {e}")
    raise
