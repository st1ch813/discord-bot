import os
import datetime
import requests
import csv
from discord.ext import tasks, commands
import discord
from flask import Flask
import threading

# Инициализация интентов и бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Функция для чтения данных из Google Таблицы
def get_text_by_time(target_time):
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            
            for row in reader:
                if len(row) >= 2:
                    sheet_time = row[0].strip()  # Время из колонки A
                    sheet_text = row[1].strip()  # Текст из колонки B
                    
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
    # На Render время идет по UTC! Прибавляем 3 часа для Киевского/Московского времени
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
    print(f"Бот {bot.user.name} успешно запущен и готов к работе!")
    if not check_schedule_and_send.is_running():
        check_schedule_and_send.start()

# --- Flask-вебсервер для удержания бота в онлайне на Render ---
app = Flask('')

@app.route('/')
def home(): 
    return "Бот работает!"

def run(): 
    app.run(host='0.0.0.0', port=10000)

def keep_alive(): 
    threading.Thread(target=run).start()

# Запуск веб-сервера
keep_alive()

# Запуск самого Дискорд-бота
bot.run(os.environ.get('DISCORD_TOKEN'))
