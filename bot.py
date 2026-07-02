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
            response.encoding = 'utf-8'
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            for row in reader:
                if len(row) >= 2:
                    sheet_time = row[0].strip()
                    sheet_text = row[1].strip()
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
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_time = now.strftime("%H:%M")
    text_to_send = get_text_by_time(current_time)
    if text_to_send:
        channel_id = int(os.environ.get('DISCORD_CHANNEL_ID'))
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(text_to_send)
            print(f"Успешно отправлено сообщение для времени {current_time}")

# Тестовая команда для проверки связи с Google Таблицей
@bot.command(name="тест")
async def test_sheet(ctx):
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            data_preview = "Содержимое таблицы, которое видит бот:\n"
            for row in reader:
                if len(row) >= 2:
                    data_preview += f"Время: `{row[0]}` | Текст: `{row[1]}`\n"
            await ctx.send(data_preview if len(data_preview) > 40 else "Таблица пустая или нечитаемая!")
        else:
            await ctx.send(f"Ошибка подключения к таблице! Статус: {response.status_code}")
    except Exception as e:
        await ctx.send(f"Произошла ошибка при тесте: {e}")

# Запуск таймера при старте бота
@bot.event
async def on_ready():
    print(f"Бот {bot.user.name} успешно запущен и готов к работе!")
    if not check_schedule_and_send.is_running():
        check_schedule_and_send.start()

# --- Простой Flask-вебсервер без ломающих стилей ---
app = Flask('')

@app.route('/')
def home():
    is_ready = bot.is_ready()
    status = "РАБОТАЕТ" if is_ready else "ЗАГРУЖАЕТСЯ/ОТКЛЮЧЕН"
    bot_name = bot.user.name if is_ready else "Неизвестно"
    ping = round(bot.latency * 1000) if is_ready else 0
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_time = now.strftime("%H:%M:%S")
    loop_status = "Запущен" if check_schedule_and_send.is_running() else "Остановлен"
    
    return f"Бот: {bot_name} | Статус: {status} | Пинг: {ping}мс | Время сервера: {current_time} | Таймер: {loop_status}"

def run(): 
    app.run(host='0.0.0.0', port=10000)

def keep_alive(): 
    threading.Thread(target=run).start()

# Запуск веб-сервера и бота
keep_alive()
bot.run(os.environ.get('DISCORD_TOKEN'))
