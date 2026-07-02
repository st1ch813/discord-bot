import os
import datetime
import requests
import csv
from discord.ext import tasks, commands
import discord
from flask import Flask, jsonify, render_template_string
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

# --- Flask-вебсервер с кнопкой управления ---
app = Flask('')

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Мониторинг Бота</title>
    <style>
        body { font-family: sans-serif; background: #121214; color: #e1e1e6; padding: 40px; text-align: center; }
        .container { background: #202024; padding: 25px; border-radius: 8px; display: inline-block; text-align: left; min-width: 320px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
        h1 { margin-top: 0; color: #04d361; font-size: 24px; }
        .param { margin: 12px 0; font-size: 16px; }
        .value { color: #8257e5; font-weight: bold; }
        .btn { 
            display: block; width: 100%; padding: 12px; margin-top: 20px; 
            border: none; border-radius: 6px; font-size: 16px; font-weight: bold; 
            cursor: pointer; color: #fff; transition: background 0.2s;
        }
        .btn-stop { background: #e04141; }
        .btn-stop:hover { background: #c93535; }
        .btn-start { background: #04d361; }
        .btn-start:hover { background: #03b855; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Панель управления Ботом</h1>
        <div class="param">Статус: <span id="status" class="value">Загрузка...</span></div>
        <div class="param">Имя бота: <span id="bot_name" class="value">...</span></div>
        <div class="param">Пинг Дискорда: <span id="ping" class="value">0</span> мс</div>
        <div class="param">Время сервера (КВ/МСК): <span id="time" class="value">00:00:00</span></div>
        <div class="param">Таймер рассылки: <span id="loop" class="value">...</span></div>
        
        <button id="toggle-btn" class="btn btn-stop" onclick="toggleBot()">Загрузка кнопки...</button>
    </div>

    <script>
        async function updateStats() {
            try {
                let res = await fetch('/api/stats');
                let data = await res.json();
                document.getElementById('status').innerText = data.status;
                document.getElementById('bot_name').innerText = data.bot_name;
                document.getElementById('ping').innerText = data.ping;
                document.getElementById('loop').innerText = data.loop_status;
                
                let btn = document.getElementById('toggle-btn');
                if (data.loop_active) {
                    btn.innerText = "ОСТАНОВИТЬ РАССЫЛКУ";
                    btn.className = "btn btn-stop";
                } else {
                    btn.innerText = "ЗАПУСТИТЬ РАССЫЛКУ";
                    btn.className = "btn btn-start";
                }
            } catch(e) {
                document.getElementById('status').innerText = "ОТКЛЮЧЕН";
            }
        }

        async function toggleBot() {
            let btn = document.getElementById('toggle-btn');
            btn.disabled = true;
            try {
                let res = await fetch('/api/toggle', { method: 'POST' });
                let data = await res.json();
                await updateStats();
            } catch(e) {
                alert("Не удалось изменить состояние бота");
            }
            btn.disabled = false;
        }

        setInterval(() => {
            let now = new Date();
            let utc = now.getTime() + (now.getTimezoneOffset() * 60000);
            let targetTime = new Date(utc + (3600000 * 3));
            document.getElementById('time').innerText = targetTime.toTimeString().split(' ')[0];
        }, 1000);

        setInterval(updateStats, 3000);
        updateStats();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/api/stats')
def get_stats():
    is_ready = bot.is_ready()
    loop_active = check_schedule_and_send.is_running()
    
    if not is_ready:
        status_text = "ЗАГРУЖАЕТСЯ"
    elif loop_active:
        status_text = "РАБОТАЕТ 24/7"
    else:
        status_text = "ПАУЗА (РАССЫЛКА ОТКЛЮЧЕНА)"

    return jsonify({
        "status": status_text,
        "bot_name": bot.user.name if is_ready else "Неизвестно",
        "ping": round(bot.latency * 1000) if is_ready else 0,
        "loop_status": "Активен" if loop_active else "Остановлен",
        "loop_active": loop_active
    })

@app.route('/api/toggle', methods=['POST'])
def toggle_loop():
    if check_schedule_and_send.is_running():
        check_schedule_and_send.stop()
        return jsonify({"success": True, "action": "stopped"})
    else:
        check_schedule_and_send.start()
        return jsonify({"success": True, "action": "started"})

def run(): 
    app.run(host='0.0.0.0', port=10000)

def keep_alive(): 
    threading.Thread(target=run).start()

# Запуск веб-сервера и бота
keep_alive()
bot.run(os.environ.get('DISCORD_TOKEN'))
