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

# --- Flask-вебсервер с красивой панелью мониторинга ---
app = Flask('')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
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

# --- Flask-вебсервер с красивой панелью мониторинга ---
app = Flask('')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Мониторинг Дискорд Бота</title>
    <meta http-equiv="refresh" content="5"> <!-- Обновление страницы каждые 5 секунд -->
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #1e1e2e;
            color: #cdd6f4;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .card {
            background-color: #252538;
            padding: 30px;
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            text-align: center;
            width: 320px;
        }
        h2 { margin-top: 0; color: #f5c2e7; }
        .status-container {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            font-size: 1.2rem;
            font-weight: bold;
            margin: 20px 0;
            padding: 10px 20px;
            border-radius: 30px;
            background-color: #181825;
        }
        .dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        .online-dot { background-color: #a6e3a1; box-shadow: 0 0 10px #a6e3a1; }
        .offline-dot { background-color: #f38ba8; box-shadow: 0 0 10px #f38ba8; }
        .online-text { color: #a6e3a1; }
        .offline-text { color: #f38ba8; }
        .info {
            font-size: 0.9rem;
            color: #a6adc8;
            text-align: left;
            line-height: 1.6;
            border-top: 1px solid #45475a;
            padding-top: 15px;
            margin-top: 15px;
        }
        .info span { color: #89b4fa; font-weight: 500; }
    </style>
</head>
<body>
    <div class="card">
        <h2>KontraktiBot</h2>
        
        {% if is_ready %}
            <div class="status-container">
                <div class="dot online-dot"></div>
                <span class="online-text">РАБОТАЕТ 24/7</span>
            </div>
        {% else %}
            <div class="status-container">
                <div class="dot offline-dot"></div>
                <span class="offline-text">ОТКЛЮЧЕН</span>
            </div>
        {% endif %}

        <div class="info">
            <div>Имя бота: <span>{{ bot_name }}</span></div>
            <div>Пинг Дискорда: <span>{{ ping }} мс</span></div>
            <div>Время сервера (КВ/МСК): <span>{{ current_time }}</span></div>
            <div>Фоновый таймер: <span>{{ loop_status }}</span></div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    is_ready = bot.is_ready()
    bot_name = bot.user.name if is_ready else "Не определено"
    ping = round(bot.latency * 1000) if is_ready else 0
    
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_time = now.strftime("%H:%M:%S")
    
    loop_status = "Запущен" if check_schedule_and_send.is_running() else "Остановлен"
    
    return render_template_string(
        HTML_TEMPLATE,
        is_ready=is_ready,
        bot_name=bot_name,
        ping=ping,
        current_time=current_time,
        loop_status=loop_status
    )

def run(): 
    app.run(host='0.0.0.0', port=10000)

def keep_alive(): 
    threading.Thread(target=run).start()

# Запуск веб-сервера
keep_alive()

# Запуск самого Дискорд-бота
bot.run(os.environ.get('DISCORD_TOKEN'))
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

# Тестовая команда для проверки связи с Google Таблицей
@bot.command(name="тест")
async def test_sheet(ctx):
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'  # Корректная кодировка для кириллицы
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
