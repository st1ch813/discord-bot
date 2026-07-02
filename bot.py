import os
import datetime
import requests
import csv
from discord.ext import tasks, commands
import discord
from flask import Flask, jsonify, render_template_string
import threading

# ================= НАСТРОЙКА РОЛИ =================
ROLE_ID = "СЮДА_ВСТАВЬ_ID_РОЛИ"
# ==================================================

# Инициализация интентов и бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Переменная для хранения точного времени запуска бота
start_time = None

# Вспомогательная функция для парсинга времени из таблицы (в формат "HH:MM")
def parse_time(time_str):
    try:
        time_str = time_str.strip()
        if not time_str:
            return None
        if len(time_str.split(':')[0]) == 1:
            time_str = "0" + time_str
        return time_str[:5]
    except:
        return None

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
                    time_part = row[0].strip()
                    if not time_part: # Пропускаем абсолютно пустые строки
                        continue
                    times_list = time_part.split()
                    for single_time in times_list:
                        sheet_time = parse_time(single_time)
                        sheet_text = row[1].strip()
                        if sheet_time == target_time:
                            return sheet_text
    except Exception as e:
        print(f"Ошибка при обращении к таблице: {e}")
    return None

# Функция для поиска следующего запланированного сообщения
def get_next_message_info():
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_minutes = now.hour * 60 + now.minute
    
    next_text = "Нет запланированных сообщений"
    time_left_str = "--"
    min_diff = 9999
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            
            for row in reader:
                if len(row) >= 2:
                    time_part = row[0].strip()
                    if not time_part:
                        continue
                    times_list = time_part.split()
                    for single_time in times_list:
                        sheet_time = parse_time(single_time)
                        if not sheet_time:
                            continue
                        
                        t_hours, t_mins = map(int, sheet_time.split(':'))
                        sheet_minutes = t_hours * 60 + t_mins
                        
                        diff = sheet_minutes - current_minutes
                        if diff <= 0:
                            diff += 1440
                            
                        if diff < min_diff:
                            min_diff = diff
                            next_text = row[1].strip()
            
            if min_diff != 9999:
                if min_diff >= 60:
                    time_left_str = f"{min_diff // 60} ч. {min_diff % 60} мин."
                else:
                    time_left_str = f"{min_diff} мин."
    except Exception as e:
        next_text = f"Ошибка проверки: {e}"
        
    return next_text, time_left_str

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
            if ROLE_ID and ROLE_ID.isdigit():
                final_text = f"<@&{ROLE_ID}>\n{text_to_send}"
            else:
                final_text = text_to_send
                
            await channel.send(final_text)
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
            has_rows = False
            for row in reader:
                if len(row) >= 2:
                    time_part = row[0].strip()
                    text_part = row[1].strip()
                    # Если строка полностью пустая — игнорируем её и не выводим в !тест
                    if not time_part and not text_part:
                        continue
                    
                    has_rows = True
                    display_time = time_part if time_part else "[Пусто]"
                    display_text = text_part[:50] if text_part else "[Пусто]"
                    data_preview += f"Времена: `{display_time}` | Текст: `{display_text}...`\n"
            
            if has_rows:
                await ctx.send(data_preview)
            else:
                await ctx.send("Таблица пустая или нечитаемая!")
        else:
            await ctx.send(f"Ошибка подключения к таблице! Status: {response.status_code}")
    except Exception as e:
        await ctx.send(f"Произошла ошибка при тесте: {e}")

# Команда !логи
@bot.command(name="логи")
async def show_logs(ctx):
    global start_time
    if start_time is None:
        await ctx.send("Ошибка: время запуска бота не зафиксировано.")
        return

    uptime = datetime.datetime.utcnow() - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    next_msg, next_time = get_next_message_info()
    ping = round(bot.latency * 1000)

    report = (
        "📊 **СТАТИСТИКА И СТАТУС БОТА**\n"
        f"⏱ **Время работы (Uptime):** `{days} дн. {hours} ч. {minutes} мин. {seconds} сек.`\n"
        f"📶 **Текущий пинг:** `{ping} мс`\n"
        f"📅 **Следующая отправка через:** `{next_time}`\n"
        f"📝 **Текст следующего сообщения:** `{next_msg[:100]}`"
    )
    await ctx.send(report)

# Запуск таймера при старте бота
@bot.event
async def on_ready():
    global start_time
    if start_time is None:
        start_time = datetime.datetime.utcnow()
        
    print(f"Бот {bot.user.name} успешно запущен и готов к работе!")
    if not check_schedule_and_send.is_running():
        check_schedule_and_send.start()

# --- Flask-вебсервер ---
app = Flask('')

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Мониторинг Бота</title>
    <style>
        body { font-family: sans-serif; background: #121214; color: #e1e1e6; padding: 40px; text-align: center; }
        .container { background: #202024; padding: 25px; border-radius: 8px; display: inline-block; text-align: left; min-width: 350px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
        h1 { margin-top: 0; color: #04d361; font-size: 24px; }
        .param { margin: 12px 0; font-size: 16px; }
        .value { color: #8257e5; font-weight: bold; }
        .next-box { background: #181825; padding: 12px; border-radius: 6px; margin-top: 15px; border-left: 4px solid #89b4fa; }
        .next-title { font-size: 14px; color: #a6adc8; margin-bottom: 5px; }
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
        
        <div class="next-box">
            <div class="next-title">СЛЕДУЮЩЕЕ СООБЩЕНИЕ:</div>
            <div id="next_text" style="font-weight: bold; word-break: break-all; color: #f5c2e7;">Загрузка...</div>
            <div style="margin-top: 5px; font-size: 14px;">Отправка через: <span id="next_time" style="color: #a6e3a1; font-weight: bold;">--</span></div>
        </div>
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
                document.getElementById('next_text').innerText = data.next_msg;
                document.getElementById('next_time').innerText = data.next_time_left;
            } catch(e) {
                document.getElementById('status').innerText = "ОТКЛЮЧЕН";
            }
        }

        setInterval(() => {
            let now = new Date();
            let utc = now.getTime() + (now.getTimezoneOffset() * 60000);
            let targetTime = new Date(utc + (3600000 * 3));
            document.getElementById('time').innerText = targetTime.toTimeString().split(' ')[0];
        }, 1000);

        setInterval(updateStats, 4000);
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
    else:
        status_text = "РАБОТАЕТ 24/7"

    next_msg, next_time_left = get_next_message_info()

    return jsonify({
        "status": status_text,
        "bot_name": bot.user.name if is_ready else "Неизвестно",
        "ping": round(bot.latency * 1000) if is_ready else 0,
        "loop_status": "Активен" if loop_active else "Остановлен",
        "next_msg": next_msg,
        "next_time_left": next_time_left
    })

def run(): 
    app.run(host='0.0.0.0', port=10000)

def keep_alive(): 
    threading.Thread(target=run).start()

# Запуск веб-сервера и бота
keep_alive()
bot.run(os.environ.get('DISCORD_TOKEN'))
