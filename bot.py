# ===== SERVER =====
GUILD_ID = 1497989819198865458

# ===== HLAVNÍ ROLE PRO VĚTŠINU COMMANDŮ =====
ALLOWED_COMMAND_ROLE_ID = 1506277397173899324

# ===== SPECIÁLNÍ ROLE PRO VYBRANÉ COMMANDY =====
SPECIAL_COMMAND_ROLE_ID = 1497989819198865459

# ===== KANÁLY =====
WELCOME_CHANNEL_ID = 1497989821841543199
RULES_CHANNEL_ID = 1506279399912378460
LOG_CHANNEL_ID = 1506260785536434286
PUNISH_LOG_CHANNEL_ID = 1506261047076585552
REVERT_LOG_CHANNEL_ID = 1506260975333015673
STRIKE_CHANNEL_ID = 1506258761440956476
APP_INFO_CHANNEL_ID = 1495083810570895463
LA_TERRAZA_TEXT_CHANNEL_ID = 1495083810570895462
ROLES_TEXT_CHANNEL_ID = 1495083810352795798

# ===== RADIO =====
RADIO_CHANNEL_ID = 1497989825037467830
RADIO_ROLE_ID = 1497989819198865460
RADIO_DATA_FILE = "radio.json"

# ===== MEETING / ACTIVITY SYSTÉM =====
MEETING_ANNOUNCEMENT_CHANNEL_ID = 1497989823867129898
MEETING_ATTENDANCE_CHANNEL_ID = 1506280054634844340
MEETING_DATA_FILE = "meetings.json"
MEETING_YES_EMOJI = "✅"
MEETING_NO_EMOJI = "❌"

# ===== MESSAGE LOG CHANNEL =====
MESSAGE_LOG_CHANNEL_ID = 1506260835964551311

# ===== AUTO ROLE =====
AUTO_ROLE_IDS = [
    1497989819198865460,
]

# ===== RADIO COMMAND =====
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
        await interaction.response.send_message(
            f"✅ Radio panel byl odeslán do {channel.mention}.",
            ephemeral=True
        )

# update
