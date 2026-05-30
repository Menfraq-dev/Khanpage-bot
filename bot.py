import os
import json
import asyncio
import threading
import random
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
GUILD_ID = 1497331142419021926

# ===== HLAVNÍ ROLE PRO VĚTŠINU COMMANDŮ =====
ALLOWED_COMMAND_ROLE_ID = 1497331142851035179

# ===== SPECIÁLNÍ ROLE PRO VYBRANÉ COMMANDY =====
SPECIAL_COMMAND_ROLE_ID = 1510335483337511094

# ===== KANÁLY =====
WELCOME_CHANNEL_ID = 1497331143517933632
RULES_CHANNEL_ID = 1510283940026384514
LOG_CHANNEL_ID = 1510334883669475551
PUNISH_LOG_CHANNEL_ID = 1510335000568926470
REVERT_LOG_CHANNEL_ID = 1510334963432689734
STRIKE_CHANNEL_ID = 1510296943388000276
APP_INFO_CHANNEL_ID = 1510284009920266315
ROLES_TEXT_CHANNEL_ID = 1510283877128601850
LA_TERRAZA_TEXT_CHANNEL_ID = 1510283877128601850

# ===== RADIO =====
# Pokud radio na novém serveru nepoužíváš, nech to takhle. Command jen napíše, že kanál nenašel.
RADIO_CHANNEL_ID = 1510290282019688618
RADIO_ROLE_ID = 0
RADIO_DATA_FILE = "radio.json"

# ===== MEETING / ACTIVITY SYSTÉM =====
# Pokud meeting systém nepoužíváš, nech 0.
MEETING_ANNOUNCEMENT_CHANNEL_ID = 0
MEETING_ATTENDANCE_CHANNEL_ID = 0
MEETING_DATA_FILE = "meetings.json"
MEETING_YES_EMOJI = "✅"
MEETING_NO_EMOJI = "❌"

# ===== WEEKLY TASK SYSTEM =====
TASK_DATA_FILE = "tasks.json"

TASK_GROUPS = {
    1: {
        "channel_id": 1497331144470036527,
        "role_id": 1510335904420593804,
        "name": "GROUP 1",
        "checklist_role_id": 1510336021751922768,
    },
    2: {
        "channel_id": 1510303581767598142,
        "role_id": 1510335935286345919,
        "name": "GROUP 2",
        "checklist_role_id": 1510336063573458994,
    },
}

TASK_LEADER_ROLE_ID = 1510335483337511094  # fallback pro starší tasky
task_deadline_loop_started = False

# ===== MESSAGE LOG CHANNEL =====
MESSAGE_LOG_CHANNEL_ID = 1510334920080232478

# ===== AUTO ROLE =====
AUTO_ROLE_IDS = [
    1497331142825873546,
    1497331142825873547,
]

# ===== OBRÁZEK =====
THUMBNAIL_PATH = "le_bruine_noir_logo.png"

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

radio_message_id = None


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
# RADIO STORAGE
# =========================
def generate_frequency() -> str:
    # rozsah 1.99 až 999.99
    value = random.randint(199, 99999) / 100
    return f"{value:.2f}"


def load_radio_data():
    default_data = {
        "primary": generate_frequency(),
        "secondary": generate_frequency(),
        "active": "primary"
    }

    if not os.path.exists(RADIO_DATA_FILE):
        save_radio_data(default_data)
        return default_data

    try:
        with open(RADIO_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("primary", generate_frequency())
        data.setdefault("secondary", generate_frequency())
        data.setdefault("active", "primary")

        if data["active"] not in ["primary", "secondary"]:
            data["active"] = "primary"

        return data
    except Exception:
        save_radio_data(default_data)
        return default_data


def save_radio_data(data):
    with open(RADIO_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_active_frequency(data) -> str:
    return data["primary"] if data.get("active") == "primary" else data["secondary"]


def get_active_label(data) -> str:
    return "PRIMÁRNÍ" if data.get("active") == "primary" else "SEKUNDÁRNÍ"


def build_radio_embed(guild: discord.Guild, data: dict) -> discord.Embed:
    active_frequency = get_active_frequency(data)
    active_label = get_active_label(data)

    embed = discord.Embed(
        title="📡 RADIO PANEL",
        description=(
            "## AKTUÁLNÍ FREKVENCE\n"
            f"# `{active_frequency}` MHz\n\n"
            f"**Aktuálně jste na:** `{active_label}`\n\n"
            f"🔵 **Primární frekvence:** `{data['primary']}` MHz\n"
            f"🟠 **Sekundární frekvence:** `{data['secondary']}` MHz\n\n"
            "Používejte tlačítka níže pro správu vysílačky."
        ),
        color=discord.Color.orange()
    )

    embed.set_author(
        name="Le Bruine Noir",
        icon_url=guild.icon.url if guild.icon else None
    )

    embed.set_footer(text="Le Bruine Noir")
    return embed


class RadioView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Status", emoji="📡", style=discord.ButtonStyle.secondary, custom_id="radio_status")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_radio_data()
        await interaction.response.send_message(
            (
                f"📡 **Aktuální frekvence:** `{get_active_frequency(data)}` MHz\n"
                f"**Aktuálně jste na:** `{get_active_label(data)}`\n"
                f"🔵 Primární: `{data['primary']}` MHz\n"
                f"🟠 Sekundární: `{data['secondary']}` MHz"
            ),
            ephemeral=True
        )

    @discord.ui.button(label="Změna frekvence", emoji="⚙️", style=discord.ButtonStyle.primary, custom_id="radio_change")
    async def change_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = {
            "primary": generate_frequency(),
            "secondary": generate_frequency(),
            "active": "primary"
        }
        save_radio_data(data)

        await interaction.response.edit_message(
            embed=build_radio_embed(interaction.guild, data),
            view=self
        )

        try:
            await interaction.channel.send(
                "📡 **Změna frekvencí! Přepnuto na PRIMÁRNÍ frekvenci.**",
                delete_after=60
            )
        except Exception:
            pass

    @discord.ui.button(label="Přepnout", emoji="🔁", style=discord.ButtonStyle.success, custom_id="radio_switch")
    async def switch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_radio_data()
        data["active"] = "secondary" if data.get("active") == "primary" else "primary"
        save_radio_data(data)

        await interaction.response.edit_message(
            embed=build_radio_embed(interaction.guild, data),
            view=self
        )

        try:
            await interaction.channel.send(
                f"📡 **Přepnuto na {get_active_label(data)} frekvenci!**",
                delete_after=60
            )
        except Exception:
            pass

    @discord.ui.button(label="PANIC", emoji="🚨", style=discord.ButtonStyle.danger, custom_id="radio_panic")
    async def panic_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_radio_data()
        data["active"] = "secondary"
        save_radio_data(data)

        await interaction.response.edit_message(
            embed=build_radio_embed(interaction.guild, data),
            view=self
        )

        role_mention = f"<@&{RADIO_ROLE_ID}>"
        try:
            await interaction.channel.send(
                f"{role_mention} 🚨 **PANIC! Okamžitě přepnout na SEKUNDÁRNÍ frekvenci!**",
                delete_after=60
            )
        except Exception:
            pass



# =========================
# MEETING STORAGE / ATTENDANCE
# =========================
def load_meeting_data():
    if not os.path.exists(MEETING_DATA_FILE):
        return {}

    try:
        with open(MEETING_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_meeting_data(data):
    with open(MEETING_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def get_reaction_members(message: discord.Message, emoji: str) -> list[discord.Member | discord.User]:
    users = []

    for reaction in message.reactions:
        if str(reaction.emoji) != emoji:
            continue

        async for user in reaction.users():
            if user.bot:
                continue
            users.append(user)

    return users


def format_user_list(users: list[discord.Member | discord.User]) -> str:
    if not users:
        return "*Nikdo zatím neodpověděl*"

    return "\n".join(user.mention for user in users[:50])


def build_meeting_embed(
    guild: discord.Guild,
    meeting_message: discord.Message,
    yes_users: list[discord.Member | discord.User],
    no_users: list[discord.Member | discord.User]
) -> discord.Embed:
    preview = meeting_message.content.strip() if meeting_message.content else "*Meeting zpráva bez textu*"
    preview = chunk_text(preview, 700)

    embed = discord.Embed(
        title="📅 MEETING ODPOVĚDI",
        description=(
            f"**Meeting:** [Klikni pro otevření zprávy]({meeting_message.jump_url})\n\n"
            f"**Text meetingu:**\n{preview}\n\n"
            f"✅ **Přijdou ({len(yes_users)}):**\n{format_user_list(yes_users)}\n\n"
            f"❌ **Nepřijdou ({len(no_users)}):**\n{format_user_list(no_users)}"
        ),
        color=discord.Color.orange()
    )

    embed.set_author(
        name="Le Bruine Noir",
        icon_url=guild.icon.url if guild.icon else None
    )

    embed.set_footer(text="Meeting attendance • Le Bruine Noir")
    return embed


async def update_meeting_attendance(guild: discord.Guild, meeting_message_id: int):
    announcement_channel = guild.get_channel(MEETING_ANNOUNCEMENT_CHANNEL_ID)
    attendance_channel = guild.get_channel(MEETING_ATTENDANCE_CHANNEL_ID)

    if not announcement_channel or not attendance_channel:
        print("❌ Meeting kanály nebyly nalezeny.")
        return

    try:
        meeting_message = await announcement_channel.fetch_message(meeting_message_id)
    except discord.NotFound:
        print("❌ Meeting zpráva nebyla nalezena.")
        return
    except Exception as e:
        print(f"❌ Chyba při načítání meeting zprávy: {e}")
        return

    yes_users = await get_reaction_members(meeting_message, MEETING_YES_EMOJI)
    no_users = await get_reaction_members(meeting_message, MEETING_NO_EMOJI)

    embed = build_meeting_embed(guild, meeting_message, yes_users, no_users)

    data = load_meeting_data()
    meeting_key = str(meeting_message_id)
    attendance_message_id = data.get(meeting_key)

    if attendance_message_id:
        try:
            attendance_message = await attendance_channel.fetch_message(int(attendance_message_id))
            await attendance_message.edit(embed=embed)
            return
        except discord.NotFound:
            data.pop(meeting_key, None)
            save_meeting_data(data)
        except Exception as e:
            print(f"❌ Chyba při editování meeting panelu: {e}")

    try:
        attendance_message = await attendance_channel.send(embed=embed)
        data[meeting_key] = attendance_message.id
        save_meeting_data(data)
    except Exception as e:
        print(f"❌ Chyba při vytváření meeting panelu: {e}")


async def remove_opposite_meeting_reaction(payload: discord.RawReactionActionEvent):
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(payload.message_id)
        member = guild.get_member(payload.user_id)
        if not member:
            return

        emoji = str(payload.emoji)
        opposite = MEETING_NO_EMOJI if emoji == MEETING_YES_EMOJI else MEETING_YES_EMOJI

        for reaction in message.reactions:
            if str(reaction.emoji) == opposite:
                await reaction.remove(member)
                break
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"❌ Chyba při mazání opačné reakce: {e}")



# =========================
# WEEKLY TASK SYSTEM
# =========================
def load_task_data():
    if not os.path.exists(TASK_DATA_FILE):
        return {}

    try:
        with open(TASK_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_task_data(data):
    with open(TASK_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def create_task_id(group: int) -> str:
    return f"group{group}-{int(discord.utils.utcnow().timestamp())}"


def parse_task_time(value: str):
    try:
        return discord.utils.parse_time(value)
    except Exception:
        return None


def format_remaining(deadline_iso: str) -> str:
    deadline = parse_task_time(deadline_iso)
    if not deadline:
        return "Neznámý čas"

    now = discord.utils.utcnow()
    remaining = deadline - now

    if remaining.total_seconds() <= 0:
        return "Deadline vypršel"

    days = remaining.days
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60

    if days > 0:
        return f"{days} dní {hours} hodin {minutes} minut"
    if hours > 0:
        return f"{hours} hodin {minutes} minut"
    return f"{minutes} minut"


def mentions_from_ids(user_ids: list[str]) -> str:
    if not user_ids:
        return "*Nikdo*"

    return "\n".join(f"<@{user_id}>" for user_id in user_ids[:40])


def count_role_members(guild: discord.Guild, role_id: int) -> int:
    role = guild.get_role(role_id)
    if not role:
        return 0
    return len([member for member in role.members if not member.bot])


def get_group_members(guild: discord.Guild, group: int) -> list[discord.Member]:
    group_info = TASK_GROUPS.get(group)
    if not group_info:
        return []

    role = guild.get_role(group_info["role_id"])
    if not role:
        return []

    return [member for member in role.members if not member.bot]


def get_task_checklist_role_id(group: int) -> int:
    group_info = TASK_GROUPS.get(group)
    if not group_info:
        return TASK_LEADER_ROLE_ID
    return group_info.get("checklist_role_id", TASK_LEADER_ROLE_ID)


def has_task_checklist_role(member: discord.Member, group: int) -> bool:
    checklist_role_id = get_task_checklist_role_id(group)
    return any(role.id == checklist_role_id for role in member.roles)


def build_task_embed(guild: discord.Guild, task: dict) -> discord.Embed:
    group = int(task["group"])
    group_info = TASK_GROUPS[group]
    deadline = task["deadline"]

    pending = task.get("pending", [])
    completed = task.get("completed", [])
    rejected = task.get("rejected", [])

    all_group_members = get_group_members(guild, group)
    all_group_ids = {str(member.id) for member in all_group_members}
    finished_ids = set(completed) | set(rejected) | set(pending)
    missing_ids = sorted(list(all_group_ids - finished_ids))

    status = "🔒 UZAVŘENO" if task.get("closed") else "🟢 AKTIVNÍ"

    embed = discord.Embed(
        title=f"📌 TÝDENNÍ ÚKOL — {group_info['name']}",
        description=(
            f"**Stav:** `{status}`\n\n"
            f"**Úkol:**\n{task['text']}\n\n"
            f"⏳ **Zbývá:** `{format_remaining(deadline)}`\n"
            f"📅 **Deadline:** {discord.utils.format_dt(parse_task_time(deadline), style='f') if parse_task_time(deadline) else '`Neznámý`'}\n"
            f"👥 **Členů v {group_info['name']}:** `{count_role_members(guild, group_info['role_id'])}`\n\n"
            f"📤 **Čeká na schválení ({len(pending)}):**\n{mentions_from_ids(pending)}\n\n"
            f"✅ **Splnili ({len(completed)}):**\n{mentions_from_ids(completed)}\n\n"
            f"❌ **Zamítnuto / nesplněno ({len(rejected)}):**\n{mentions_from_ids(rejected)}\n\n"
            f"⚠️ **Zatím neodevzdali ({len(missing_ids)}):**\n{mentions_from_ids(missing_ids[:20])}"
        ),
        color=discord.Color.orange() if not task.get("closed") else discord.Color.red()
    )

    embed.set_author(
        name="Task systém",
        icon_url=guild.icon.url if guild.icon else None
    )

    embed.set_footer(text="Člen klikne Odevzdat úkol • Vedení schvaluje v PM")
    return embed


async def edit_task_panel(guild: discord.Guild, task_id: str):
    data = load_task_data()
    task = data.get(task_id)
    if not task:
        return

    group = int(task["group"])
    group_info = TASK_GROUPS.get(group)
    if not group_info:
        return

    channel = guild.get_channel(group_info["channel_id"])
    if not channel:
        print(f"❌ Task group kanál nebyl nalezen pro group {group}.")
        return

    message_id = task.get("message_id")
    if not message_id:
        return

    try:
        message = await channel.fetch_message(int(message_id))
        await message.edit(embed=build_task_embed(guild, task), view=TaskPanelView(task_id) if not task.get("closed") else None)
    except discord.NotFound:
        print(f"❌ Task panel nebyl nalezen: {task_id}")
    except Exception as e:
        print(f"❌ Chyba při editaci task panelu: {e}")


async def notify_leaders_about_submission(guild: discord.Guild, task_id: str, member: discord.Member):
    data = load_task_data()
    task = data.get(task_id)
    if not task:
        return

    group = int(task["group"])
    checklist_role_id = get_task_checklist_role_id(group)
    checklist_role = guild.get_role(checklist_role_id)

    if not checklist_role:
        print(f"❌ Checklist role pro GROUP {group} nebyla nalezena.")
        return

    embed = discord.Embed(
        title="📨 Nové odevzdání úkolu",
        description=(
            f"👤 **Uživatel:** {member.mention}\n"
            f"🆔 **User ID:** `{member.id}`\n"
            f"📌 **Group:** `{task['group']}`\n\n"
            f"**Úkol:**\n{task['text']}\n\n"
            f"⏰ **Odevzdáno:** {discord.utils.format_dt(discord.utils.utcnow(), style='f')}"
        ),
        color=discord.Color.orange()
    )

    embed.set_footer(text=f"Schválit může pouze checklist role pro GROUP {group}.")
    view = TaskApprovalView(task_id, member.id)

    sent = 0
    for leader in checklist_role.members:
        if leader.bot:
            continue
        try:
            await leader.send(embed=embed, view=view)
            sent += 1
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"❌ Nepodařilo se poslat PM checklistu: {e}")

    if sent == 0:
        print(f"⚠️ PM checklistu pro GROUP {group} se neposlala nikomu. Možná mají vypnuté DMs.")


class TaskPanelView(discord.ui.View):
    def __init__(self, task_id: str):
        super().__init__(timeout=None)
        self.task_id = task_id

    @discord.ui.button(label="Odevzdat úkol", emoji="📤", style=discord.ButtonStyle.primary)
    async def submit_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Tento button jde použít jen na serveru.", ephemeral=True)
            return

        data = load_task_data()
        task = data.get(self.task_id)

        if not task:
            await interaction.response.send_message("❌ Task nebyl nalezen.", ephemeral=True)
            return

        if task.get("closed"):
            await interaction.response.send_message("❌ Tento task už je uzavřený.", ephemeral=True)
            return

        group = int(task["group"])
        group_info = TASK_GROUPS[group]
        group_role = interaction.guild.get_role(group_info["role_id"])

        if not group_role or group_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Tento úkol není pro tvoji group.", ephemeral=True)
            return

        user_id = str(interaction.user.id)

        if user_id in task.get("completed", []):
            await interaction.response.send_message("✅ Tento úkol už máš schválený.", ephemeral=True)
            return

        if user_id in task.get("pending", []):
            await interaction.response.send_message("⏳ Už čekáš na schválení vedením.", ephemeral=True)
            return

        if user_id in task.get("rejected", []):
            task["rejected"].remove(user_id)

        task.setdefault("pending", []).append(user_id)
        data[self.task_id] = task
        save_task_data(data)

        await edit_task_panel(interaction.guild, self.task_id)
        await notify_leaders_about_submission(interaction.guild, self.task_id, interaction.user)

        await interaction.response.send_message(
            "📤 Úkol byl odeslán ke schválení vedením.",
            ephemeral=True
        )

    @discord.ui.button(label="Aktualizovat", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Tento button jde použít jen na serveru.", ephemeral=True)
            return

        data = load_task_data()
        task = data.get(self.task_id)

        if not task:
            await interaction.response.send_message("❌ Task nebyl nalezen.", ephemeral=True)
            return

        group = int(task["group"])

        if not has_task_checklist_role(interaction.user, group):
            await interaction.response.send_message("❌ Aktualizovat panel může jen checklist role pro tvoji group.", ephemeral=True)
            return

        await edit_task_panel(interaction.guild, self.task_id)
        await interaction.response.send_message("✅ Panel aktualizován.", ephemeral=True)


class TaskApprovalView(discord.ui.View):
    def __init__(self, task_id: str, target_user_id: int):
        super().__init__(timeout=None)
        self.task_id = task_id
        self.target_user_id = str(target_user_id)

    async def check_leader(self, interaction: discord.Interaction) -> bool:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            await interaction.response.send_message("❌ Server nebyl nalezen.", ephemeral=True)
            return False

        member = guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message("❌ Nejsi nalezen na serveru.", ephemeral=True)
            return False

        data = load_task_data()
        task = data.get(self.task_id)
        if not task:
            await interaction.response.send_message("❌ Task nebyl nalezen.", ephemeral=True)
            return False

        group = int(task["group"])

        if not has_task_checklist_role(member, group):
            await interaction.response.send_message("❌ Nemáš oprávnění schvalovat tasky pro tuto group.", ephemeral=True)
            return False

        return True

    @discord.ui.button(label="Schválit", emoji="✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_leader(interaction):
            return

        guild = bot.get_guild(GUILD_ID)
        data = load_task_data()
        task = data.get(self.task_id)

        if not task:
            await interaction.response.send_message("❌ Task nebyl nalezen.", ephemeral=True)
            return

        if self.target_user_id in task.get("pending", []):
            task["pending"].remove(self.target_user_id)

        if self.target_user_id in task.get("rejected", []):
            task["rejected"].remove(self.target_user_id)

        if self.target_user_id not in task.get("completed", []):
            task.setdefault("completed", []).append(self.target_user_id)

        data[self.task_id] = task
        save_task_data(data)

        if guild:
            await edit_task_panel(guild, self.task_id)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(content="✅ Úkol byl schválen.", view=self)

    @discord.ui.button(label="Zamítnout", emoji="❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_leader(interaction):
            return

        guild = bot.get_guild(GUILD_ID)
        data = load_task_data()
        task = data.get(self.task_id)

        if not task:
            await interaction.response.send_message("❌ Task nebyl nalezen.", ephemeral=True)
            return

        if self.target_user_id in task.get("pending", []):
            task["pending"].remove(self.target_user_id)

        if self.target_user_id in task.get("completed", []):
            task["completed"].remove(self.target_user_id)

        if self.target_user_id not in task.get("rejected", []):
            task.setdefault("rejected", []).append(self.target_user_id)

        data[self.task_id] = task
        save_task_data(data)

        if guild:
            await edit_task_panel(guild, self.task_id)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(content="❌ Úkol byl zamítnut.", view=self)


async def close_task_if_expired(guild: discord.Guild, task_id: str):
    data = load_task_data()
    task = data.get(task_id)
    if not task or task.get("closed"):
        return

    deadline = parse_task_time(task["deadline"])
    if not deadline or discord.utils.utcnow() < deadline:
        return

    group = int(task["group"])
    members = get_group_members(guild, group)

    completed = set(task.get("completed", []))
    rejected = set(task.get("rejected", []))

    for member in members:
        user_id = str(member.id)
        if user_id not in completed and user_id not in rejected:
            task.setdefault("rejected", []).append(user_id)

    task["pending"] = []
    task["closed"] = True
    data[task_id] = task
    save_task_data(data)

    await edit_task_panel(guild, task_id)


async def task_deadline_worker():
    await bot.wait_until_ready()

    while not bot.is_closed():
        guild = bot.get_guild(GUILD_ID)
        if guild:
            data = load_task_data()
            for task_id in list(data.keys()):
                task = data.get(task_id, {})
                if task.get("closed"):
                    continue
                await close_task_if_expired(guild, task_id)
                await edit_task_panel(guild, task_id)

        await asyncio.sleep(600)

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
    global task_deadline_loop_started

    bot.add_view(RadioView())

    task_data = load_task_data()
    for task_id, task in task_data.items():
        if not task.get("closed"):
            bot.add_view(TaskPanelView(task_id))

    if not task_deadline_loop_started:
        bot.loop.create_task(task_deadline_worker())
        task_deadline_loop_started = True

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
                f"• Nezapomeň si přečíst <#1510283940026384514>\n"
                f"📅 Account created: {created_at}"
            ),
            color=discord.Color.orange()
        )

        embed.set_author(
            name=str(member),
            icon_url=member.display_avatar.url
        )

        if os.path.exists(THUMBNAIL_PATH):
            file = discord.File(THUMBNAIL_PATH, filename="le_bruine_noir_logo.png")
            embed.set_thumbnail(url="attachment://le_bruine_noir_logo.png")
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
# MEETING REACTION SYSTEM
# =========================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild and message.channel.id == MEETING_ANNOUNCEMENT_CHANNEL_ID:
        try:
            await message.add_reaction(MEETING_YES_EMOJI)
            await message.add_reaction(MEETING_NO_EMOJI)
            await update_meeting_attendance(message.guild, message.id)
        except discord.Forbidden:
            print("❌ Bot nemá oprávnění přidávat reakce nebo posílat meeting panel.")
        except Exception as e:
            print(f"❌ Chyba v meeting systému: {e}")

    await bot.process_commands(message)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.guild_id is None:
        return

    if bot.user and payload.user_id == bot.user.id:
        return

    if payload.channel_id != MEETING_ANNOUNCEMENT_CHANNEL_ID:
        return

    if str(payload.emoji) not in [MEETING_YES_EMOJI, MEETING_NO_EMOJI]:
        return

    await remove_opposite_meeting_reaction(payload)

    guild = bot.get_guild(payload.guild_id)
    if guild:
        await asyncio.sleep(0.5)
        await update_meeting_attendance(guild, payload.message_id)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.guild_id is None:
        return

    if payload.channel_id != MEETING_ANNOUNCEMENT_CHANNEL_ID:
        return

    if str(payload.emoji) not in [MEETING_YES_EMOJI, MEETING_NO_EMOJI]:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild:
        await update_meeting_attendance(guild, payload.message_id)


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
        file = discord.File(THUMBNAIL_PATH, filename="le_bruine_noir_logo.png")
        embed.set_thumbnail(url="attachment://le_bruine_noir_logo.png")
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


@bot.tree.command(name="sendcartel", description="Pošle Le Bruine Noir lore do určeného kanálu.", guild=guild_obj)
async def sendcartel_slash(interaction: discord.Interaction):
    if not await check_command_role(interaction):
        return

    channel = interaction.guild.get_channel(LA_TERRAZA_TEXT_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Cílový kanál nebyl nalezen.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    part1 = (
        "**Le Bruine Noir**\n\n"
        "Le Bruine Noir je označení pro staré korejské pouliční gangy a organizovaný zločin, který vznikal v temných částech Soulu, Busanu a Incheonu. "
        "Už od 80. a 90. let si tahle jména lidé spojovali s brutalitou, disciplínou a naprostou loajalitou ke své rodině.\n\n"
        "Na první pohled působili jako obyčejní podnikatelé, majitelé barů, heren nebo nočních klubů. "
        "Ve skutečnosti ale stáli za výpalným, nelegálním hazardem, ochranou podniků, pašováním a tichým odstraňováním problémů.\n\n"
        "Le Bruine Noir nikdy nebyl o zbytečném hluku. "
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
        "Když se objeví problém, Le Bruine Noir ho vyřeší rychle, čistě a bez zbytečných otázek."
    )

    part3 = (
        "Dnes je Le Bruine Noir v Los Santos známé jméno mezi lidmi, kteří vědí, kam se dívat.\n\n"
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
                f"📨 **Le Bruine Noir Lore Sent**\n"
                f"📍 **Channel:** {channel.mention}"
            ),
            moderator_text=interaction.user.mention,
            thumbnail_user=interaction.user
        )

        await interaction.followup.send("✅ Le Bruine Noir lore bylo odesláno.", ephemeral=True)

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
        "# 『 HIERARCHIE ORGANIZACE 』\n\n"

        "## **Patron**\n"
        "```"
        "Hlava organizace určující směr frakce a rozhodující o nejdůležitějších záležitostech."
        "```\n\n"

        "## **Jefe del Jefes**\n"
        "```"
        "Pravá ruka Patrona dohlížející na chod organizace a koordinaci vedení."
        "```\n\n"

        "## **El Jefe**\n"
        "```"
        "Vysoce postavený člen vedení organizující důležité akce a dohled nad strukturou."
        "```\n\n"

        "## **Sub Jefe**\n"
        "```"
        "Nižší vedení zajišťující disciplínu a komunikaci mezi členy organizace."
        "```\n\n"

        "## **Capitán de capitanes**\n"
        "```"
        "Respektovaný velitel koordinující členy a menší operace organizace."
        "```\n\n"

        "## **Captain**\n"
        "```"
        "Člen command struktury vedoucí členy v terénu a předávající rozkazy vedení."
        "```\n\n"

        "## **Asociado de Honor**\n"
        "```"
        "Prověřený a respektovaný člen s důvěrou vedení a silným postavením ve frakci."
        "```\n\n"

        "## **Sicario**\n"
        "```"
        "Specializovaný člen určený pro nebezpečné a citlivé úkoly organizace."
        "```\n\n"

        "## **Soldado**\n"
        "```"
        "Plnohodnotný člen organizace reprezentující jméno frakce v ulicích."
        "```"
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
# WEEKLY TASK COMMANDS
# =========================
@bot.tree.command(name="task", description="Vytvoří týdenní úkol pro group.", guild=guild_obj)
@app_commands.describe(
    group="Vyber group 1, 2 nebo 3",
    ukol="Text úkolu",
    days="Deadline v dnech, defaultně 7"
)
async def task_slash(interaction: discord.Interaction, group: int, ukol: str, days: int = 7):
    if not await check_special_command_role(interaction):
        return

    if group not in TASK_GROUPS:
        await interaction.response.send_message("❌ Group musí být 1, 2 nebo 3.", ephemeral=True)
        return

    if days < 1 or days > 30:
        await interaction.response.send_message("❌ Deadline může být 1 až 30 dní.", ephemeral=True)
        return

    group_info = TASK_GROUPS[group]
    channel = interaction.guild.get_channel(group_info["channel_id"])

    if not channel:
        await interaction.response.send_message("❌ Group kanál nebyl nalezen.", ephemeral=True)
        return

    task_id = create_task_id(group)
    deadline = discord.utils.utcnow() + timedelta(days=days)

    task = {
        "id": task_id,
        "group": group,
        "text": ukol,
        "created_by": str(interaction.user.id),
        "created_at": discord.utils.utcnow().isoformat(),
        "deadline": deadline.isoformat(),
        "pending": [],
        "completed": [],
        "rejected": [],
        "closed": False,
        "message_id": None,
    }

    embed = build_task_embed(interaction.guild, task)
    message = await channel.send(embed=embed, view=TaskPanelView(task_id))

    task["message_id"] = message.id

    data = load_task_data()
    data[task_id] = task
    save_task_data(data)

    await interaction.response.send_message(
        f"✅ Task pro **{group_info['name']}** byl vytvořen v {channel.mention}.",
        ephemeral=True
    )


@bot.tree.command(name="taskstatus", description="Ukáže přehled aktivních tasků.", guild=guild_obj)
async def taskstatus_slash(interaction: discord.Interaction):
    if not await check_special_command_role(interaction):
        return

    data = load_task_data()
    active_tasks = [task for task in data.values() if not task.get("closed")]

    if not active_tasks:
        await interaction.response.send_message("📭 Žádný aktivní task.", ephemeral=True)
        return

    lines = []
    for task in active_tasks[:10]:
        group = int(task["group"])
        lines.append(
            f"**GROUP {group}** — ⏳ `{format_remaining(task['deadline'])}`\\n"
            f"✅ {len(task.get('completed', []))} | 📤 {len(task.get('pending', []))} | ❌ {len(task.get('rejected', []))}\\n"
            f"{chunk_text(task['text'], 120)}"
        )

    embed = discord.Embed(
        title="📊 TASK STATUS",
        description="\\n\\n".join(lines),
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# RADIO COMMAND
# =========================
@bot.tree.command(name="radio", description="Otevře radio panel.", guild=guild_obj)
@app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
async def radio_slash(interaction: discord.Interaction):
    channel = interaction.guild.get_channel(RADIO_CHANNEL_ID)

    if not channel:
        await interaction.response.send_message("❌ Radio kanál nebyl nalezen.", ephemeral=True)
        return

    data = load_radio_data()
    embed = build_radio_embed(interaction.guild, data)

    await channel.send(embed=embed, view=RadioView())

    if interaction.channel_id == RADIO_CHANNEL_ID:
        await interaction.response.send_message("✅ Radio panel byl vytvořen.", ephemeral=True)
    else:
        await interaction.response.send_message(f"✅ Radio panel byl odeslán do {channel.mention}.", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        seconds = int(error.retry_after)
        message = f"⏳ Počkej ještě {seconds} sekund před dalším použitím commandu."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return

    print(f"❌ Slash command error: {error}")

    try:
        if interaction.response.is_done():
            await interaction.followup.send("❌ Nastala chyba při použití commandu.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nastala chyba při použití commandu.", ephemeral=True)
    except Exception:
        pass


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

    embed.set_footer(text="Le Bruine Noir")

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

# UPDATE
