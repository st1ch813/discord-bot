import os
import datetime
import requests
import csv
from flask import Flask, jsonify, render_template_string, redirect, url_for
import threading
import time

# ================= НАСТРОЙКА РОЛИ =================
ROLE_ID = "1447219553259094219"
# ==================================================

# Все настройки подтягиваются напрямую из переменных окружения Render
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

# Глобальные переменные статуса
start_time = datetime.datetime.utcnow()
is_bot_enabled = True  # Флаг паузы

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
    if not expiry_str or expiry_str.strip() == "": 
        return False
    expiry_str = expiry_str.strip().replace("`", "").replace("'", "")
    if "срок" in expiry_str.lower() or "годн" in expiry_str.lower(): 
        return False
    try:
        # Смещаем время сервера на Киев/МСК (+3 часа)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
        current_date = now.date()
        
        for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d.%m.%y', '%d/%m/%Y'):
            try:
                expiry_date = datetime.datetime.strptime(expiry_str, fmt).date()
                if expiry_date == current_date: 
                    return True
            except ValueError: 
                continue
    except Exception as e:
        print(f"Ошибка парсинга даты '{expiry_str}': {e}")
    return False

# Сборка и форматирование текста для отправки в Дискорд
def format_webhook_message(text_part, ad_type, expiry_str):
    text_part = text_part.strip().replace("```", "").replace("`", "")
    ad_type = ad_type.lower().strip()
    if not text_part: 
        return None

    # Подставляем команду по цвету
    prefix = ""
    if "красн" in ad_type:
        prefix = "/adv "
    elif "зелен" in ad_type:
        prefix = "/wnews "
        
    # Заворачиваем в чистый блок кода
    code_block = f"```\n{prefix}{text_part}\n```"
    
    # Добавляем пинг роли сверху
    if ROLE_ID and ROLE_ID.isdigit():
        final_msg = f"<@&{ROLE_ID}>\n{code_block}"
    else:
        final_msg = code_block
        
    # Приписка про последний день контракта
    if check_is_last_day(expiry_str):
        final_msg += "\nсрок контракта истекает завтра"
        
    return final_msg

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
                    if not time_part or ":" not in time_part or "время" in time_part.lower(): 
                        continue
                    times_list = time_part.split()
                    for single_time in times_list:
                        sheet_time = parse_time(single_time)
                        if sheet_time == target_time:
                            text_part = row[1].strip()
                            expiry_part = row[2].strip() if len(row) >= 3 else ""
                            type_part = row[3].strip() if len(row) >= 4 else ""
                            return format_webhook_message(text_part, type_part, expiry_part)
    except Exception as e:
        print(f"Ошибка при обращении к таблице: {e}")
    return None

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
                    text_part = row[1].strip().replace("```", "").replace("`", "")
                    if not time_part or ":" not in time_part or "время" in time_part.lower() or not text_part:
                        continue
                    
                    expiry_part = row[2].strip() if len(row) >= 3 else ""
                    if "срок" in expiry_part.lower() or "годн" in expiry_part.lower():
                        expiry_part = ""
                        
                    type_part = row[3].strip() if len(row) >= 4 else "обычное"
                    if "тип" in type_part.lower():
                        type_part = "обычное"

                    contracts.append({
                        "time": time_part,
                        "text": text_part,
                        "expiry": expiry_part if expiry_part else "Не указан",
                        "type": type_part,
                        "is_last_day": check_is_last_day(expiry_part)
                    })
    except Exception as e:
        print(f"Ошибка получения контрактов: {e}")
    return contracts

def get_next_message_info():
    if not is_bot_enabled:
        return "Рассылка на паузе", "--", "", "Обычное", False

    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_minutes = now.hour * 60 + now.minute

    next_text = "Нет запланированных сообщений"
    time_left_str = "--"
    contract_expiry = ""
    ad_type_display = "Обычное"
    is_last = False
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
                    if not time_part or ":" not in time_part or "время" in time_part.lower():
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
                            next_text = row[1].strip().replace("```", "").replace("`", "")
                            contract_expiry = row[2].strip() if len(row) >= 3 and "срок" not in row[2].lower() else ""
                            ad_type_display = row[3].strip() if len(row) >= 4 and "тип" not in row[3].lower() else "Обычное"
                            is_last = check_is_last_day(contract_expiry)

            if min_diff != 9999:
                if min_diff >= 60:
                    time_left_str = f"{min_diff // 60} ч. {min_diff % 60} мин."
                else:
                    time_left_str = f"{min_diff} мин."
    except Exception as e:
        next_text = f"Ошибка проверки: {e}"

    return next_text, time_left_str, contract_expiry, ad_type_display, is_last

def send_to_webhook(final_text):
    if not WEBHOOK_URL:
        print("Ошибка: DISCORD_WEBHOOK_URL не настроен в Environment Variables!")
        return
    payload = {"content": final_text}
    try:
        res = requests.post(WEBHOOK_URL, json=payload)
        if res.status_code in [200, 204]:
            print("Сообщение успешно отправлено через Вебхук!")
        else:
            print(f"Ошибка вебхука: {res.status_code}")
    except Exception as e:
        print(f"Не удалось отправить вебхук: {e}")

# Фоновый цикл проверки времени (работает раз в минуту)
def cron_loop():
    print("Фоновый таймер вебхука запущен.")
    while True:
        if is_bot_enabled:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
            current_time = now.strftime("%H:%M")
            formatted_text = get_text_by_time(current_time)
            if formatted_text:
                send_to_webhook(formatted_text)
        time.sleep(60)

# --- Flask Веб-сервер ---
app = Flask('')

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
   <meta charset="UTF-8">
   <title>Мониторинг Контрактов (Вебхук)</title>
   <style>
       body { font-family: sans-serif; background: #121214; color: #e1e1e6; padding: 40px; text-align: center; }
       .container { background: #202024; padding: 25px; border-radius: 8px; display: inline-block; text-align: left; min-width: 700px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
       h1, h2 { margin-top: 0; color: #04d361; font-size: 24px; }
       h2 { font-size: 20px; color: #8257e5; margin-top: 25px; }
       .param { margin: 12px 0; font-size: 16px; }
       .value { color: #8257e5; font-weight: bold; }
       .status-on { color: #04d361; font-weight: bold; }
       .status-off { color: #f75a68; font-weight: bold; }
       
       .next-box { background: #181825; padding: 12px; border-radius: 6px; margin-top: 15px; margin-bottom: 15px; border-left: 4px solid #89b4fa; }
       .next-title { font-size: 14px; color: #a6adc8; margin-bottom: 5px; }

       .btn { background: #8257e5; color: white; border: none; padding: 10px 20px; border-radius: 5px; font-weight: bold; cursor: pointer; font-size: 16px; margin-top: 10px; transition: 0.2s; }
       .btn:hover { background: #9466ff; }
       .btn-pause { background: #f75a68; }
       .btn-pause:hover { background: #ff6b7b; }

       table { width: 100%; border-collapse: collapse; margin-top: 15px; background: #181825; border-radius: 6px; overflow: hidden; }
       th, td { padding: 12px; text-align: left; border-bottom: 1px solid #29292e; font-size: 14px; }
       th { background-color: #29292e; color: #04d361; font-weight: bold; }
       .td-time { color: #a6e3a1; font-weight: bold; white-space: nowrap; }
       .td-expiry { color: #f9e2af; font-weight: bold; white-space: nowrap; }
       .badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; text-transform: uppercase; }
       .badge-red { background: #f75a68; color: #fff; }
       .badge-green { background: #04d361; color: #121214; }
       .badge-normal { background: #4f545c; color: #fff; }
       .alert-expiry { color: #f75a68; font-weight: bold; font-size: 11px; display: block; margin-top: 4px; background: rgba(247,90,104,0.1); padding: 2px 6px; border-radius: 4px; text-align: center; }
   </style>
</head>
<body>
   <div class="container">
       <h1>Управление Рассылкой</h1>
       <div class="param">Статус системы: <span id="status">Загрузка...</span></div>
       <div class="param">Время сервера (КВ/МСК): <span id="time" class="value">00:00:00</span></div>
       
       <form action="/toggle" method="POST">
           <button type="submit" id="action_btn" class="btn">Загрузка...</button>
       </form>

       <div class="next-box">
           <div class="next-title">СЛЕДУЮЩИЙ КОНТРАКТ:</div>
           <div id="next_text" style="font-weight: bold; color: #f5c2e7;">Загрузка...</div>
           <div style="margin-top: 5px; font-size: 14px;">Отправка через: <span id="next_time" style="color: #a6e3a1; font-weight: bold;">--</span></div>
           <div style="margin-top: 5px; font-size: 14px;">Тип объявления: <span id="next_type" class="value">--</span></div>
           <div style="margin-top: 5px; font-size: 14px;">Срок контракта: <span id="contract_expiry" style="color: #f9e2af;">--</span> <span id="next_alert" style="color: #f75a68; font-weight: bold;"></span></div>
       </div>

       <h2>📋 Все активные контракты</h2>
       <table>
           <thead>
               <tr>
                   <th style="width: 15%;">Время</th>
                   <th style="width: 22%;">Тип объявления</th>
                   <th style="width: 43%;">Текст контракта</th>
                   <th style="width: 20%;">Срок действия</th>
               </tr>
           </thead>
           <tbody id="contracts_table_body">
               <tr><td colspan="4" style="text-align: center;">Загрузка списка...</td></tr>
           </tbody>
       </table>
   </div>

   <script>
       async function updateStats() {
           try {
               let res = await fetch('/api/stats');
               let data = await res.json();
               
               let statusElem = document.getElementById('status');
               let btn = document.getElementById('action_btn');
               
               if (data.is_enabled) {
                   statusElem.innerText = "РАБОТАЕТ ЧЕРЕЗ ВЕБХУК";
                   statusElem.className = "status-on";
                   btn.innerText = "⏸ Поставить на паузу";
                   btn.className = "btn btn-pause";
               } else {
                   statusElem.innerText = "НА ПАУЗЕ";
                   statusElem.className = "status-off";
                   btn.innerText = "▶️ Запустить рассылку";
                   btn.className = "btn";
               }

               // Инфо о следующем сообщении
               document.getElementById('next_text').innerText = data.next_msg;
               document.getElementById('next_time').innerText = data.next_time_left;
               document.getElementById('contract_expiry').innerText = data.contract_expiry || "Не указан";
               
               let nType = data.next_type;
               if(nType.includes("красн")) nType = "Красное (/adv)";
               if(nType.includes("зелен")) nType = "Зеленое (/wnews)";
               document.getElementById('next_type').innerText = nType;
               document.getElementById('next_alert').innerText = data.next_is_last ? "⚠️ ПОСЛЕДНИЙ ДЕНЬ!" : "";

               // Обновление таблицы
               let tableBody = document.getElementById('contracts_table_body');
               tableBody.innerHTML = "";
               if (data.all_contracts && data.all_contracts.length > 0) {
                   data.all_contracts.forEach(c => {
                       let row = document.createElement('tr');
                       let bClass = "badge-normal";
                       let tText = "Обычное";
                       
                       if(c.type.includes("красн")) { bClass = "badge-red"; tText = "Красное (/adv)"; }
                       if(c.type.includes("зелен")) { bClass = "badge-green"; tText = "Зеленое (/wnews)"; }
                       
                       let warn = c.is_last_day ? '<span class="alert-expiry">⚠️ ПОСЛЕДНИЙ ДЕНЬ</span>' : '';
                       
                       row.innerHTML = `
                           <td class="td-time">${c.time}</td>
                           <td><span class="badge ${bClass}">${tText}</span></td>
                           <td>${c.text}</td>
                           <td class="td-expiry">${c.expiry}${warn}</td>
                       `;
                       tableBody.appendChild(row);
                   });
               } else {
                   tableBody.innerHTML = `<tr><td colspan="4" style="text-align: center;">Таблица пуста</td></tr>`;
               }
           } catch(e) { }
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

@app.route('/toggle', methods=['POST'])
def toggle_status():
    global is_bot_enabled
    is_bot_enabled = not is_bot_enabled
    return redirect(url_for('index'))

@app.route('/api/stats')
def get_stats():
    next_msg, next_time_left, contract_expiry, next_type, next_is_last = get_next_message_info()
    return jsonify({
        "is_enabled": is_bot_enabled,
        "next_msg": next_msg,
        "next_time_left": next_time_left,
        "contract_expiry": contract_expiry,
        "next_type": next_type,
        "next_is_last": next_is_last,
        "all_contracts": get_all_contracts_from_sheet()
    })

if __name__ == '__main__':
    threading.Thread(target=cron_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
