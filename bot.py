import csv
import discord
import aiohttp
import os
from discord.ext import tasks, commands
from datetime import datetime
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# Вызови эту функцию прямо перед строкой bot.run(TOKEN)


# НАСТРОЙКИ (будут браться из настроек Render)
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEETS_ID")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

async def get_messages_from_sheet():
    url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv"
    messages = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text(encoding='utf-8')
                    reader = csv.reader(text.splitlines())
                    for row in reader:
                        if len(row) >= 2:
                            time_cell = row[0].strip()
                            text_cell = row[1].strip()
                            messages[time_cell] = text_cell
    except Exception as e:
        print(f"Ошибка при чтении таблицы: {e}")
    return messages

@bot.event
async def on_ready():
    print(f"Бот {bot.user} успешно запущен!")
    if not check_time.is_running():
        check_time.start()

@tasks.loop(seconds=60)
async def check_time():
    now = datetime.now().strftime("%H:%M")
    sheet_data = await get_messages_from_sheet()
    
    if now in sheet_data:
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            await channel.send(sheet_data[now])
            print(f"[{now}] Сообщение отправлено!")
        else:
            print(f"[{now}] Ошибка: Канал не найден.")

@check_time.before_loop
async def before_check_time():
    await bot.wait_until_ready()
keep_alive()
bot.run(TOKEN)
          
