import os
import datetime
import requests
import csv
from discord.ext import tasks, commands
import discord

# Инициализация бота (используй свой префикс или настройки)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Функция для чтения данных из Google Таблицы
def get_text_by_time(target_time):
    # Берем ID таблицы из переменных окружения Render
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    # Ссылка для экспорта таблицы в формат CSV
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Декодируем полученный текст
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            
            # Проходимся по каждой строчке таблицы
            for row in reader:
                if len(row) >= 2:
                    sheet_time = row[0].strip()  # Время из колонки A
                    sheet_text = row[1].strip()  # Текст из колонки B
                    
                    # Если время совпало с текущим, возвращаем текст
                    if sheet_time == target_time:
                        return sheet_text
        else:
            print(f"Не удалось загрузить таблицу. Статус: {response.status_code}")
    except Exception as e:
        print(f"Ошибка при обращении к таблице: {e}")
    return None

# Фоновый цикл, который проверяет время каждую минуту
@tasks.loop(minutes=1)
async def check_schedule_and_send():
    # ВНИМАНИЕ: На Render время идет по UTC! 
    # Если твое время в таблице по Киеву/Москве (UTC+3), прибавляем 3 часа:
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_time = now.strftime("%H:%M")
    
    # Ищем текст под текущую минуту
    text_to_send = get_text_by_time(current_time)
    
    if text_to_send:
        channel_id = int(os.environ.get('DISCORD_CHANNEL_ID'))
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(text_to_send)
            print(f"Успешно отправлено сообщение для времени {current_time}")

# Запуск таймера при старте бота
@bot.event
async def on_ready():
    print(f"Бот {bot.user.name} успешно запущен!")
    if not check_schedule_and_send.is_running():
        check_schedule_and_send.start()

# --- Твой Flask-код для удержания бота в онлайне (keep_alive) ---
from flask import Flask
import threading

app = Flask('')
@app.route('/')
def home(): return "Бот работает!"
def run(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): threading.Thread(target=run).start()

keep_alive()
# Запуск бота по токену из Render
bot.run(os.environ.get('DISCORD_TOKEN'))
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
          
