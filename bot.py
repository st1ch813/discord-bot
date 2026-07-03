import os
import datetime
import requests
import csv
from discord.ext import tasks, commands
import discord
from flask import Flask, jsonify, render_template_string
import threading

# ================= НАСТРОЙКА РОЛИ =================
ROLE_ID = "1447219553259094219"
# ==================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

start_time = None
is_bot_enabled = True  # Флаг работы рассылки

def parse_time(time_str):
    try:
        time_str = time_str.strip()
        if not time_str or ":" not in time_str:
            return None
        if len(time_str.split(':')[0]) == 1:
            time_str = "0" + time_str
        return time_str[:5]
    except:
        return None

# Функция проверки: является ли сегодня ПОСЛЕДНИМ днем контракта
def check_is_last_day(expiry_str):
    if not expiry_str or expiry_str.strip() == "" or "срок" in expiry_str.lower():
        return False
    try:
        expiry_str = expiry_str.strip()
        # Время сервера смещаем на +3 (Киев/МСК) для точной даты
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
        
        expiry_date = None
        for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d.%m.%y'):
            try:
                expiry_date = datetime.datetime.strptime(expiry_str, fmt).date()
                break
            except ValueError:
                continue
                
        if expiry_date and expiry_date == now.date():
            return True
    except Exception as e:
        print(f"Ошибка проверки даты контракта: {e}")
    return False

# Сборка финального сообщения с тегами и префиксами
def format_announcement(text_part, ad_type, expiry_str):
    text_part = text_part.strip()
    ad_type = ad_type.lower().strip()
    
    # Подставляем команду по цвету из колонки D
    prefix = ""
    if "красн" in ad_type:
        prefix = "/adv "
    elif "зелен" in ad_type:
        prefix = "/wnews "
        
    # Формируем блок кода автоматически, тебе больше не надо писать ``` ручками
    code_block = f"```\n{prefix}{text_part}\n```"
    
    # Добавляем пинг роли сверху, если она указана
    if ROLE_ID and ROLE_ID.isdigit():
        final_msg = f"<@&{ROLE_ID}>\n{code_block}"
    else:
        final_msg = code_block
        
    # Если сегодня последний день контракта — добавляем приписку СНИЗУ (вне блока кода)
    if check_is_last_day(expiry_str):
        final_msg += "\nСрок контракта истекает завтра"
        
    return final_msg

# Поиск текста для отправки в текущую минуту
def get_text_by_time(target_time):
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"[https://docs.google.com/spreadsheets/d/](https://docs.google.com/spreadsheets/d/){sheet_id}/export?format=csv"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            for row in reader:
                if len(row) >= 2:
                    time_part = row[0].strip()
                    if not time_part or ":" not in time_part: 
                        continue
                    times_list = time_part.split()
                    for single_time in times_list:
                        sheet_time = parse_time(single_time)
                        if sheet_time == target_time:
                            text_part = row[1].strip()
                            expiry_part = row[2].strip() if len(row) >= 3 else ""
                            type_part = row[3].strip() if len(row) >= 4 else ""
                            return format_announcement(text_part, type_part, expiry_part)
    except Exception as e:
        print(f"Ошибка при обращении к таблице: {e}")
    return None

# Данные для сайта и логов
def get_next_message_info():
    if not is_bot_enabled:
        return "Рассылка на паузе", "--", "", ""

    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"[https://docs.google.com/spreadsheets/d/](https://docs.google.com/spreadsheets/d/){sheet_id}/export?format=csv"
    
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_minutes = now.hour * 60 + now.minute
    
    next_text = "Нет запланированных сообщений"
    time_left_str = "--"
    contract_expiry = ""
    ad_type_display = "Обычное"
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
                    if not time_part or ":" not in time_part:
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
                            contract_expiry = row[2].strip() if len(row) >= 3 and "срок" not in row[2].lower() else ""
                            ad_type_display = row[3].strip() if len(row) >= 4 and "тип" not in row[3].lower() else "Обычное"
            
            if min_diff != 9999:
                if min_diff >= 60:
                    time_left_str = f"{min_diff // 60} ч. {min_diff % 60} мин."
                else:
                    time_left_str = f"{min_diff} мин."
    except Exception as e:
        next_text = f"Ошибка проверки: {e}"
        
    return next_text, time_left_str, contract_expiry, ad_type_display

def get_all_contracts_from_sheet():
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"[https://docs.google.com/spreadsheets/d/](https://docs.google.com/spreadsheets/d/){sheet_id}/export?format=csv"
    contracts = []
    try:
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            for row in reader:
                if len(row) >= 2:
                    time_part = row[0].strip()
                    text_part = row[1].strip()
                    if ":" not in time_part or "время" in time_part.lower():
                        continue
                        
                    expiry_part = row[2].strip() if len(row) >= 3 else ""
                    if "срок" in expiry_part.lower(): expiry_part = ""
                    
                    type_part = row[3].strip() if len(row) >= 4 else "обычное"
                    if "тип" in type_part.lower(): type_part = "обычное"

                    contracts.append({
                        "time": time_part,
                        "text": text_part,
                        "expiry": expiry_part if expiry_part else "Не указан",
                        "type": type_part if type_part else "обычное"
                    })
    except Exception as e:
        print(f"Ошибка получения всех контрактов: {e}")
    return contracts

@tasks.loop(minutes=1)
async def check_schedule_and_send():
    if not is_bot_enabled:
        return

    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_time = now.strftime("%H:%M")
    final_content = get_text_by_time(current_time)
    if final_content:
        channel_id = int(os.environ.get('DISCORD_CHANNEL_ID'))
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(final_content)
            print(f"Успешно отправлено сообщение для времени {current_time}")

@bot.command(name="пауза")
async def toggle_bot(ctx):
    global is_bot_enabled
    is_bot_enabled = not is_bot_enabled
    if is_bot_enabled:
        await ctx.send("Бот не на паузе (работает)")
    else:
        await ctx.send("Бот на паузе")

@bot.command(name="тест")
async def test_sheet(ctx):
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"[https://docs.google.com/spreadsheets/d/](https://docs.google.com/spreadsheets/d/){sheet_id}/export?format=csv"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            data_preview = f"Содержимое таблицы, которое видит бот (Рассылка: {'ВКЛ' if is_bot_enabled else 'ПАУЗА'}):\n"
            has_rows = False
            for row in reader:
                if len(row) >= 2:
                    time_part = row[0].strip()
                    text_part = row[1].strip()
                    if ":" not in time_part: continue
                    has_rows = True
                    display_text = text_part[:30]
                    expiry_part = f" | Срок: `{row[2].strip()}`" if len(row) >= 3 and row[2].strip() and "срок" not in row[2].lower() else ""
                    type_part = f" | Тип: `{row[3].strip()}`" if len(row) >= 4 and row[3].strip() and "тип" not in row[3].lower() else ""
                    data_preview += f"Время: `{time_part}` | Текст: `{display_text}...`{expiry_part}{type_part}\n"
            if has_rows:
                await ctx.send(data_preview)
            else:
                await ctx.send("Таблица пустая!")
        else:
            await ctx.send(f"Ошибка таблицы! Status: {response.status_code}")
    except Exception as e:
        await ctx.send(f"Ошибка при тесте: {e}")

@bot.command(name="логи")
async def show_logs(ctx):
    global start_time
    if start_time is None: return
    uptime = datetime.datetime.utcnow() - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    next_msg, next_time, expiry, ad_type = get_next_message_info()
    ping = round(bot.latency * 1000)
    status_str = "🟢 РАБОТАЕТ" if is_bot_enabled else "🟡 НА ПАУЗЕ"
    
    report = (
        "📊 **СТАТИСТИКА И СТАТУС БОТА**\n"
        f"⚙️ **Режим рассылки:** `{status_str}`\n"
        f"⏱ **Время работы:** `{days} дн. {hours} ч. {minutes} мин.`\n"
        f"📶 **Пинг:** `{ping} мс`\n"
        f"📅 **Следующая отправка через:** `{next_time}`\n"
        f"🎨 **Тип объявления:** `{ad_type}`\n"
        f"📝 **Текст:** `{next_msg[:60]}...`\n"
        f"⏳ **Срок контракта:** `{expiry if expiry else 'Не указа
