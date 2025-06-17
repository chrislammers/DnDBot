import discord
import openai
from dotenv import load_dotenv
import os
import asyncio
import json
from collections import defaultdict, deque

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
discord_token = os.getenv("DISCORD_BOT_TOKEN")

# Load or initialize player data
try:
    with open("players.json", "r") as f:
        player_data = json.load(f)
except FileNotFoundError:
    player_data = {}

def save_player_data():
    with open("players.json", "w") as f:
        json.dump(player_data, f, indent=2)

def resolve_player_name(input_name):
    input_name = input_name.strip().lower()
    for stored_name, data in player_data.items():
        if stored_name.lower() == input_name:
            return stored_name
        for alias in data.get("aliases", []):
            if alias.strip().lower() == input_name:
                return stored_name
    return None

def format_player_stats(name):
    data = player_data.get(name)
    if not data:
        return None
    lines = [
        f"**{name.capitalize()}** ({data.get('race', 'Unknown Race')} {data.get('class', 'Unknown Class')})",
        f"**HP:** {data.get('current_hp', '?')}/{data.get('hp', '?')} | **AC:** {data.get('ac', '?')}",
        f"**DEX:** {data.get('dex', '?')} | **DEX Mod:** {data.get('dex_mod', '?')}"
    ]
    if "weapons" in data:
        lines.append("**Weapons:** " + ", ".join(data["weapons"]))
    if "features" in data:
        lines.append("**Features:**")
        for feat in data["features"]:
            lines.append(f"- {feat}")
    return "\n".join(lines)

def get_player_context(message_content):
    context_strings = []
    lower_msg = message_content.lower()
    for name, stats in player_data.items():
        if name.lower() in lower_msg:
            stats_str = ", ".join(f"{k.capitalize()}={v}" for k, v in stats.items() if isinstance(v, (str, int)))
            context_strings.append(f"{name.capitalize()}: {stats_str}")
    return "\n".join(context_strings)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

conversation_histories = defaultdict(list)
turn_order = defaultdict(deque)

system_prompt = {
    "role": "system",
    "content": (
        "You are a GPT-4-powered Dungeon Master assistant running a dark horror-themed D&D 5e campaign. "
        "Use eerie, mysterious, and immersive gothic descriptions. "
        "Keep responses concise and focused, about 3-5 sentences. Avoid repeating phrases or overly detailed narration."
    )
}

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = " ".join(message.content.strip().split())
    parts = content.split()
    if not parts:
        return

    command = parts[0].lower()
    args = parts[1:]

    if command == "!stats" and args:
        resolved_name = resolve_player_name(args[0])
        if not resolved_name:
            await message.channel.send("Character not found.")
            return
        stats = format_player_stats(resolved_name)
        await message.channel.send(stats)
        return

    if command == "!hp" and len(args) >= 2:
        resolved_name = resolve_player_name(args[0])
        if not resolved_name:
            await message.channel.send("Character not found.")
            return
        try:
            change = int(args[1])
            data = player_data[resolved_name]
            data["current_hp"] = max(0, min(data["hp"], data["current_hp"] + change))
            save_player_data()
            await message.channel.send(f"{resolved_name.capitalize()}'s HP is now {data['current_hp']}/{data['hp']}.")
        except ValueError:
            await message.channel.send("Invalid HP change amount.")
        return

    if command == "!inv" and args:
        resolved_name = resolve_player_name(args[0])
        if not resolved_name:
            await message.channel.send("Character not found.")
            return
        data = player_data[resolved_name]
        if "inventory" in data:
            await message.channel.send(f"**{resolved_name.capitalize()}'s Inventory:**\n" + "\n".join(f"- {item}" for item in data["inventory"]))
        else:
            await message.channel.send("No inventory found.")
        return

    if command == "!spells" and args:
        resolved_name = resolve_player_name(args[0])
        if not resolved_name:
            await message.channel.send("Character not found.")
            return
        data = player_data[resolved_name]
        if "spells" in data:
            await message.channel.send(f"**{resolved_name.capitalize()}'s Spells:**\n" + "\n".join(f"- {s}" for s in data["spells"]))
        else:
            await message.channel.send("No spells found.")
        return

    if command == "!party":
        characters = ", ".join(name.capitalize() for name in player_data)
        await message.channel.send(f"**Party Members:** {characters}")
        return

    if command == "!turn":
        queue = turn_order[message.channel.id]
        if queue:
            await message.channel.send(f"**Current Turn:** {queue[0].capitalize()}")
        else:
            await message.channel.send("No turn order set. Use `!resetturn name1 name2 ...`")
        return

    if command == "!next":
        queue = turn_order[message.channel.id]
        if queue:
            queue.rotate(-1)
            await message.channel.send(f"**Next Turn:** {queue[0].capitalize()}")
        else:
            await message.channel.send("No turn order set.")
        return

    if command == "!skip":
        queue = turn_order[message.channel.id]
        if not queue:
            await message.channel.send("No turn order set. Use `!resetturn` first.")
            return
        skipped = queue[0].capitalize()
        queue.rotate(-1)
        await message.channel.send(f"⏭️ **{skipped}'s turn skipped.** Next up: **{queue[0].capitalize()}**")
        return

    if command == "!resetturn" and args:
        resolved_names = []
        not_found = []
        for name in args:
            resolved = resolve_player_name(name)
            if resolved:
                resolved_names.append(resolved)
            else:
                not_found.append(name)
        if not_found:
            await message.channel.send(f"Characters not found: {', '.join(not_found)}")
            return
        turn_order[message.channel.id] = deque(resolved_names)
        await message.channel.send(f"Turn order reset: {', '.join(name.capitalize() for name in resolved_names)}")
        return

    if command == "!dm" and len(args) >= 2:
        input_name = args[0].lower()
        action = " ".join(args[1:])

        if input_name != "party":
            resolved_name = resolve_player_name(input_name)
            if not resolved_name:
                await message.channel.send("Character not found.")
                return

            queue = turn_order[message.channel.id]
            if not queue:
                await message.channel.send("No turn order set. Use `!resetturn` first.")
                return
            current_turn = queue[0].lower()
            if resolved_name.lower() != current_turn:
                await message.channel.send(f"It's not {resolved_name.capitalize()}'s turn! Current turn: **{queue[0].capitalize()}**")
                return
        else:
            resolved_name = "The party"

        player_context = get_player_context(action)
        if player_context:
            action += f"\n\n[Player Context]\n{player_context}"

        history = conversation_histories[message.channel.id]
        history.append({"role": "user", "content": f"{resolved_name.capitalize()} attempts: {action}"})

        if len(history) > 10:
            history = history[-10:]
            conversation_histories[message.channel.id] = history

        messages = [system_prompt] + list(history)

        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=150,
                temperature=0.4,
                top_p=0.7
            )
            reply = response.choices[0].message.content if response.choices else "No response from AI."
            history.append({"role": "assistant", "content": reply})
            await message.channel.send(f"**{resolved_name.capitalize()}**: {reply}")
        except Exception as e:
            await message.channel.send(f"Error: {str(e)}")
            return

        if input_name != "party":
            queue.rotate(-1)
            await message.channel.send(f"🔄 **Next Turn:** {queue[0].capitalize()}")
        return

    if command == "!addplayer" and len(args) >= 7:
        name = args[0].strip()
        race = args[1]
        char_class = args[2]
        try:
            hp = int(args[3])
            ac = int(args[4])
            dex = int(args[5])
        except ValueError:
            await message.channel.send("HP, AC, and DEX must be numbers.")
            return

        background = args[6]
        alignment = args[7] if len(args) > 7 else "Neutral"

        inventory, weapons, spells, features, aliases = [], [], [], [], []

        for arg in args[8:]:
            if "=" not in arg:
                continue
            key, value = arg.split("=", 1)
            items = [item.strip() for item in value.split(",") if item.strip()]
            if key == "inventory":
                inventory.extend(items)
            elif key == "weapons":
                weapons.extend(items)
            elif key == "spells":
                spells.extend(items)
            elif key == "features":
                features.extend(items)
            elif key == "aliases":
                aliases.extend(items)

        normalized_name = name.lower()
        if normalized_name in (n.lower() for n in player_data):
            await message.channel.send("A character with that name already exists.")
            return

        player_data[normalized_name] = {
            "class": char_class,
            "race": race,
            "alignment": alignment,
            "background": background,
            "hp": hp,
            "current_hp": hp,
            "ac": ac,
            "dex": dex,
            "dex_mod": (dex - 10) // 2,
            "inventory": inventory,
            "weapons": weapons,
            "spells": spells,
            "features": features,
            "aliases": aliases
        }
        save_player_data()
        await message.channel.send(f"Character **{name}** has been added to the party!")
        return

    if command == "!addalias" and len(args) >= 2:
        input_name = args[0]
        new_aliases = [alias.strip() for alias in " ".join(args[1:]).split(",") if alias.strip()]

        resolved_name = resolve_player_name(input_name)
        if not resolved_name:
            await message.channel.send("Character not found.")
            return

        char_data = player_data[resolved_name]
        if "aliases" not in char_data:
            char_data["aliases"] = []

        added_aliases = []
        for alias in new_aliases:
            if alias.lower() not in [a.lower() for a in char_data["aliases"]]:
                char_data["aliases"].append(alias)
                added_aliases.append(alias)

        if added_aliases:
            save_player_data()
            await message.channel.send(f"Added aliases for **{resolved_name.capitalize()}**: {', '.join(added_aliases)}")
        else:
            await message.channel.send("No new aliases were added (they may already exist).")
        return

    if command == "!listaliases" and args:
        resolved_name = resolve_player_name(args[0])
        if not resolved_name:
            await message.channel.send("Character not found.")
            return
        aliases = player_data[resolved_name].get("aliases", [])
        if aliases:
            await message.channel.send(f"**Aliases for {resolved_name.capitalize()}:** {', '.join(aliases)}")
        else:
            await message.channel.send(f"{resolved_name.capitalize()} has no aliases.")
        return

    if command == "!commandlist":
        await message.channel.send("""
**Available Commands:**
- `!dm [name] [action]`: Narrate a player's turn (only if it's their turn)
- `!dm party [action]`: Narrate a group action (always allowed)
- `!stats [name]`: Show a character’s stats
- `!hp [name] +/-[value]`: Adjust a character’s HP
- `!inv [name]`: Show character’s inventory
- `!spells [name]`: Show character’s spells
- `!party`: List all known characters
- `!turn`: Show current turn
- `!next`: Move to the next turn
- `!skip`: Skip the current character's turn
- `!resetturn [name1 name2 ...]`: Set the initiative order
- `!addplayer ...`: Create a character (with optional inventory, aliases, etc.)
- `!addalias [name] [alias1,alias2,...]`: Add one or more aliases for a character
- `!listaliases [name]`: Show a character’s aliases
- `!commandlist`: Show this list
""")
        return

client.run(discord_token)
