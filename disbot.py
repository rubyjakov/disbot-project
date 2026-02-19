import discord
from discord.ext import commands
import aiohttp
import os
from dotenv import load_dotenv
import json


load_dotenv()
riot_api_key = os.getenv("RIOT_API_KEY")
discord_token = os.getenv("DISCORD_TOKEN")


intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


ALLOWED_CHANNEL_NAME = "command-channel"

RANK_ORDER = {
    "IRON": 1, "BRONZE": 2, "SILVER": 3, "GOLD": 4, "PLATINUM": 5,
    "EMERALD": 6, "DIAMOND": 7, "MASTER": 8, "GRANDMASTER": 9, "CHALLENGER": 10
}
DIV_ORDER = {"IV": 1, "III": 2, "II": 3, "I": 4}




def load_user():
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)


async def update_member_nick(member, puuid):
    async with aiohttp.ClientSession() as session:
        rank_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}?api_key={riot_api_key}"
        async with session.get(rank_url) as resp:
            if resp.status == 200:
                rank_data = await resp.json()
                user_tier = "UNRANKED"
                user_rank = ""

                for entry in rank_data:
                    if entry["queueType"] == "RANKED_SOLO_5x5":
                        user_tier = entry["tier"]
                        user_rank = entry["rank"]
                        break

                base_name = member.display_name.split(" [")[0]

                if user_tier == "UNRANKED":
                    new_nick = f"{base_name} [Unranked]"
                else:
                    new_nick = f"{base_name} [{user_tier.capitalize()}-{user_rank}]"

                try:
                    await member.edit(nick=new_nick[:32])
                except Exception as e:
                    print(f"Failed to edit nick for {member.name}: {e}")




@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('------')


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    users = load_user()
    user_id_str = str(member.id)
    if before.channel is None and after.channel is not None and user_id_str in users:

        await update_member_nick(member, users[user_id_str])




@bot.command()
async def register(ctx, *, riot_id: str):

    if ctx.channel.name != ALLOWED_CHANNEL_NAME:
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send(f"❌ {ctx.author.mention}, Use this command only in #{ALLOWED_CHANNEL_NAME}!", delete_after=10)
        return

    if "#" not in riot_id:
        await ctx.send("❌ Please include your tag: Name#Tag")
        return

    name, tag = riot_id.split("#", 1)
    name, tag = name.strip(), tag.strip()

    async with aiohttp.ClientSession() as session:
        account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}?api_key={riot_api_key}"
        async with session.get(account_url) as resp:
            if resp.status == 200:
                data = await resp.json()
                puuid = data['puuid']
                users = load_user()
                users[str(ctx.author.id)] = puuid
                save_users(users)
                await ctx.send(f"✅ {ctx.author.mention}, registered successfully! (Account: {name}#{tag})")
                await update_member_nick(ctx.author, puuid)
            else:
                await ctx.send(f"❌ Player **{name}#{tag}** not found. Check your spelling!")


@bot.command()
async def myrank(ctx):
    users = load_user()
    user_id = str(ctx.author.id)
    if user_id not in users:
        await ctx.send(f"❌ {ctx.author.mention}, you are not registered! Use `!register Name#Tag` first.")
        return

    puuid = users[user_id]
    async with aiohttp.ClientSession() as session:
        rank_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}?api_key={riot_api_key}"
        async with session.get(rank_url) as resp:
            data = await resp.json()
            stats = "No Ranked Solo data found."
            for entry in data:
                if entry["queueType"] == "RANKED_SOLO_5x5":
                    stats = (f"**Rank:** {entry['tier']} {entry['rank']}\n"
                             f"**LP:** {entry['leaguePoints']}\n"
                             f"**Winrate:** {entry['wins']}W / {entry['losses']}L")
                    break
            embed = discord.Embed(title=f"📊 Status for {ctx.author.display_name}", description=stats,
                                  color=discord.Color.green())
            await ctx.send(embed=embed)


@bot.command()
async def ladder(ctx):
    users = load_user()
    if not users:
        await ctx.send("The ladder is empty!")
        return

    waiting_msg = await ctx.send("⏳ Fetching ranks for the leaderboard...")
    leaderboard = []

    async with aiohttp.ClientSession() as session:
        for user_id, puuid in users.items():
            rank_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}?api_key={riot_api_key}"
            async with session.get(rank_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tier, div, lp = "UNRANKED", "IV", 0
                    for entry in data:
                        if entry["queueType"] == "RANKED_SOLO_5x5":
                            tier, div, lp = entry["tier"], entry["rank"], entry["leaguePoints"]
                            break
                    score = (RANK_ORDER.get(tier, 0) * 10000) + (DIV_ORDER.get(div, 0) * 1000) + lp
                    member = ctx.guild.get_member(int(user_id))
                    display_name = member.display_name if member else f"User_{user_id}"
                    leaderboard.append(
                        {"name": display_name, "rank_str": f"{tier.capitalize()} {div}", "lp": lp, "score": score})

    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    embed = discord.Embed(title="🏆 Server Top 5 - Solo Queue", color=discord.Color.gold())
    for i, player in enumerate(leaderboard[:5], 1):
        medal = ["🥇", "🥈", "🥉", "👤", "👤"][i - 1]
        embed.add_field(name=f"{medal} #{i} - {player['name']}", value=f"**{player['rank_str']}** ({player['lp']} LP)",
                        inline=False)

    await waiting_msg.delete()
    await ctx.send(embed=embed)



@bot.command()
async def clear(ctx, amount: int):

    if not ctx.channel.permissions_for(ctx.me).manage_messages:
        await ctx.send("❌ לי (הבוט) אין הרשאות למחוק הודעות בשרת הזה!", delete_after=5)
        return

    if amount <= 0:
        await ctx.send("❌ נא לציין מספר חיובי של הודעות למחיקה.", delete_after=5)
        return

    try:

        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"✅ נמחקו {len(deleted) - 1} הודעות.", delete_after=3)
    except Exception as e:
        await ctx.send(f"❌ שגיאה בניסיון המחיקה: {e}", delete_after=3)


@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ שכחת לציין כמה הודעות למחוק! לדוגמה: `!clear 10`", delete_after=5)
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ נא להזין מספר תקין.", delete_after=3)

bot.run(discord_token)