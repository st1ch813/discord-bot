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

# Вспомогательная функция для парсинга времени из таблицы (в формат "HH:MM")
def parse_time(time_str):
    try:
        time_str = time_str.strip()
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
                    sheet_time = parse_time(row[0])
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
                    sheet_time = parse_time(row[0])
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

# --- Flask-вебсервер ---
app = Flask('')

HTML_PAGE
