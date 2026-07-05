import os
import datetime
import requests
import csv
from flask import Flask, jsonify, render_template_string, redirect, url_for, session, request
import threading
import time
import warnings

# Отключаем предупреждения о парсинге дат, чтобы логи на Render были чистыми
warnings.filterwarnings("ignore", category=UserWarning, module="datetime")

# ================= НАСТРОЙКИ БОТА =================
ROLE_ID = "1447219553259094219"
SHEET_ID = "1B8Ts_DHQ11878tw1Qa8mUdjxFdCb249v78R10n9czBw"
# ==================================================

# Пароль для доступа к панели (берется из настроек Render, по умолчанию "1234")
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '1234')
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

# Глобальные переменные статуса и КЭШ таблицы
start_time = datetime.datetime.utcnow()
is_bot_enabled = True  # Флаг паузы
skipped_times = set()  # Множество пропущенных временных меток (например, {"18:45"})

SHEET_ROWS_CACHE = {
    "data": [],
    "last_fetched": 0
}
CACHE_TIMEOUT = 10  # Время жизни кэша в секундах

def fetch_sheet_rows():
    global SHEET_ROWS_CACHE
    now = time.time()
    if now - SHEET_ROWS_CACHE["last_fetched"] > CACHE_TIMEOUT or not SHEET_ROWS_CACHE["data"]:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
        print(f"[LOG] Запрос свежих данных из Google Таблицы...")
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                response.encoding = 'utf-8'
                lines = response.text.splitlines()
                reader = csv.reader(lines)
                parsed_rows = list(reader)
                
                # Убираем пустые строки на выходе
                filtered_rows = [r for r in parsed_rows if len(r) >= 2 and r[0].strip()]
                
                SHEET_ROWS_CACHE["data"] = filtered_rows
                SHEET_ROWS_CACHE["last_fetched"] = now
                print(f"[LOG] Успешно загружено строк из таблицы: {len(filtered_rows)}")
            else:
                print(f"[ERROR] Ошибка Google Sheets. Статус: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Исключение при запросе к таблице: {e}")
    return SHEET_ROWS_CACHE["data"]

def parse_time(time_str):
    try:
        time_str = time_str.strip().lower()
        if not time_str or ":" not in time_str:
            return None
            
        parts = time_str.split(':')
        if len(parts[0]) == 1:
            parts[0] = "0" + parts[0]
            
        return f"{parts[0][:2]}:{parts[1][:2]}"
    except:
        return None

def check_is_last_day(expiry_str):
    if not expiry_str or expiry_str.strip() == "": 
        return False
    expiry_str = expiry_str.strip().replace("`", "").replace("'", "")
    if "срок" in expiry_str.lower() or "годн" in expiry_str.lower(): 
        return False
    try:
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
        current_date = now.date()
        
        # Парсим диапазоны дат вроде "29.06-05.07" или "29.06 - 06.07"
        if "-" in expiry_str:
            parts = expiry_str.split("-")
            expiry_str = parts[1].strip()
            
        for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d.%m.%y', '%d/%m/%Y', '%d.%m'):
            try:
                if fmt == '%d.%m':
                    p_days, p_months = map(int, expiry_str.split('.'))
                    expiry_date = datetime.date(current_date.year, p_months, p_days)
                else:
                    expiry_date = datetime.datetime.strptime(expiry_str, fmt).date()
                    
                if expiry_date == current_date: 
                    return True
            except: 
                continue
    except Exception as e:
        print(f"[ERROR] Ошибка парсинга даты '{expiry_str}': {e}")
    return False

def format_webhook_message(text_part, expiry_str):
    text_part = text_part.strip()
    if not text_part: 
        return None
        
    if ROLE_ID and ROLE_ID.isdigit():
        final_msg = f"<@&{ROLE_ID}>\n{text_part}"
    else:
        final_msg = text_part
        
    if check_is_last_day(expiry_str):
        final_msg += "\nсрок контракта истекает завтра"
        
    return final_msg

def get_text_by_time(target_time):
    rows = fetch_sheet_rows()
    for row in rows:
        if len(row) >= 2:
            time_part = row[0].strip()
            if not time_part: 
                continue
            times_list = time_part.split()
            for single_time in times_list:
                sheet_time = parse_time(single_time)
                if sheet_time == target_time:
                    text_part = row[1].strip()
                    expiry_part = row[2].strip() if len(row) >= 3 else ""
                    return format_webhook_message(text_part, expiry_part)
    return None

def get_all_contracts_from_sheet():
    rows = fetch_sheet_rows()
    contracts = []
    for index, row in enumerate(rows):
        try:
            if len(row) < 2: 
                continue
                
            time_part = row[0].strip()
            text_part = row[1].strip()
            
            if not time_part or not text_part:
                continue
                
            if "время" in time_part.lower() or "текст" in text_part.lower():
                continue
                
            expiry_part = row[2].strip() if len(row) >= 3 else ""
            if "срок" in expiry_part.lower() or "годн" in expiry_part.lower():
                expiry_part = ""

            is_last = check_is_last_day(expiry_part)
            
            contracts.append({
                "time": time_part,
                "text": text_part,
                "expiry": expiry_part if expiry_part else "Не указан",
                "is_last_day": is_last
            })
        except Exception as e:
            print(f"[ERROR] Ошибка обработки строки {index}: {e}")
            
    return contracts

def get_next_execution_time():
    rows = fetch_sheet_rows()
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_minutes = now.hour * 60 + now.minute
    min_diff = 9999
    next_time_str = None

    for row in rows:
        if len(row) >= 2:
            time_part = row[0].strip()
            if not time_part:
                continue
            times_list = time_part.split()
            for single_time in times_list:
                sheet_time = parse_time(single_time)
                if not sheet_time or ":" not in sheet_time:
                    continue
                try:
                    t_hours, t_mins = map(int, sheet_time.split(':'))
                    sheet_minutes = t_hours * 60 + t_mins

                    diff = sheet_minutes - current_minutes
                    if diff <= 0:
                        diff += 1440

                    if diff < min_diff:
                        min_diff = diff
                        next_time_str = sheet_time
                except:
                    continue
    return next_time_str

def get_next_message_info():
    if not is_bot_enabled:
        return "Рассылка на паузе", "--", "", False

    rows = fetch_sheet_rows()

    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    current_minutes = now.hour * 60 + now.minute

    next_text = "Нет запланированных сообщений"
    time_left_str = "--"
    contract_expiry = ""
    is_last = False
    min_diff = 9999

    for row in rows:
        if len(row) >= 2:
            time_part = row[0].strip()
            if not time_part:
                continue
            times_list = time_part.split()
            for single_time in times_list:
                sheet_time = parse_time(single_time)
                if not sheet_time or ":" not in sheet_time:
                    continue

                try:
                    t_hours, t_mins = map(int, sheet_time.split(':'))
                    sheet_minutes = t_hours * 60 + t_mins

                    diff = sheet_minutes - current_minutes
                    if diff <= 0:
                        diff += 1440

                    if diff < min_diff:
                        min_diff = diff
                        next_text = row[1].strip()
                        contract_expiry = row[2].strip() if len(row) >= 3 and "срок" not in row[2].lower() else ""
                        is_last = check_is_last_day(contract_expiry)
                except:
                    continue

    if min_diff != 9999:
        if min_diff >= 60:
            time_left_str = f"{min_diff // 60} ч. {min_diff % 60} мин."
        else:
            time_left_str = f"{min_diff} мин."

    return next_text, time_left_str, contract_expiry, is_last

def send_to_webhook(final_text):
    if not WEBHOOK_URL:
        print("[ERROR] DISCORD_WEBHOOK_URL не настроен!")
        return
    payload = {"content": final_text}
    try:
        res = requests.post(WEBHOOK_URL, json=payload)
        if res.status_code in [200, 204]:
            print("[LOG] Сообщение успешно отправлено через Вебхук!")
        else:
            print(f"[ERROR] Ошибка вебхука: {res.status_code}")
    except Exception as e:
        print(f"[ERROR] Не удалось отправить вебхук: {e}")

def cron_loop():
    global skipped_times
    print("[LOG] Фоновый таймер вебхука запущен.")
    while True:
        if is_bot_enabled:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
            current_time = now.strftime("%H:%M")
            
            # Проверяем, пропущен ли контракт на текущее время
            if current_time in skipped_times:
                print(f"[LOG] Рассылка на время {current_time} была принудительно пропущена пользователем.")
                skipped_times.remove(current_time)  # Убираем из пропущенных, чтобы сработало завтра
            else:
                formatted_text = get_text_by_time(current_time)
                if formatted_text:
                    send_to_webhook(formatted_text)
        time.sleep(60)

app = Flask('')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'super-secret-key-for-session-signing-98765')

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
   <meta charset="UTF-8">
   <title>Мониторинг Контрактов (Вебхук)</title>
   <style>
       body { font-family: sans-serif; background: #121214; color: #e1e1e6; padding: 40px; text-align: center; margin: 0; }
       .container { background: #202024; padding: 25px; border-radius: 8px; display: inline-block; text-align: left; min-width: 700px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); position: relative; }
       
       /* Top Bar styling */
       .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #29292e; padding-bottom: 15px; }
       h1 { margin: 0; color: #04d361; font-size: 24px; }
       h2 { font-size: 20px; color: #8257e5; margin-top: 25px; margin-bottom: 15px; }
       
       .param { margin: 12px 0; font-size: 16px; }
       .value { color: #8257e5; font-weight: bold; }
       .status-on { color: #04d361; font-weight: bold; }
       .status-off { color: #f75a68; font-weight: bold; }
       
       .next-box { background: #181825; padding: 15px; border-radius: 6px; margin-top: 15px; margin-bottom: 15px; border-left: 4px solid #89b4fa; relative; }
       .next-title { font-size: 14px; color: #a6adc8; margin-bottom: 5px; }
       
       .skipped-badge { background: #f75a68; color: white; padding: 3px 6px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 10px; text-transform: uppercase; display: inline-block; }

       /* Buttons styling */
       .btn { background: #8257e5; color: white; border: none; padding: 10px 18px; border-radius: 5px; font-weight: bold; cursor: pointer; font-size: 14px; transition: 0.2s; display: inline-flex; align-items: center; gap: 8px; }
       .btn:hover { background: #9466ff; }
       .btn-secondary { background: #29292e; color: #a8a8b3; }
       .btn-secondary:hover { background: #323238; color: #e1e1e6; }
       .btn-pause { background: #f75a68; }
       .btn-pause:hover { background: #ff6b7b; }
       .btn-skip { background: #f9e2af; color: #11111b; }
       .btn-skip:hover { background: #fae0b0; }
       .btn-link { background: #3174f1; }
       .btn-link:hover { background: #4b86f4; text-decoration: none; }

       /* Custom Web UI Modals styling */
       .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; opacity: 0; pointer-events: none; transition: 0.2s; }
       .modal-overlay.show { opacity: 1; pointer-events: auto; }
       .modal-box { background: #202024; padding: 30px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.6); width: 100%; max-width: 400px; text-align: center; border: 1px solid #29292e; }
       .modal-box h3 { color: #04d361; margin-top: 0; margin-bottom: 15px; }
       .modal-box input { width: 100%; padding: 12px; background: #121214; border: 1px solid #29292e; border-radius: 5px; color: white; font-size: 16px; box-sizing: border-box; margin-bottom: 20px; outline: none; }
       .modal-box input:focus { border-color: #04d361; }
       .modal-buttons { display: flex; flex-direction: column; gap: 12px; margin-top: 15px; }
       
       table { width: 100%; border-collapse: collapse; margin-top: 15px; background: #181825; border-radius: 6px; overflow: hidden; }
       th, td { padding: 12px; text-align: left; border-bottom: 1px solid #29292e; font-size: 14px; }
       th { background-color: #29292e; color: #04d361; font-weight: bold; }
       .td-time { color: #a6e3a1; font-weight: bold; white-space: nowrap; }
       .td-expiry { color: #f9e2af; font-weight: bold; white-space: nowrap; }
       .alert-expiry { color: #f75a68; font-weight: bold; font-size: 11px; display: block; margin-top: 4px; background: rgba(247,90,104,0.1); padding: 2px 6px; border-radius: 4px; text-align: center; }
       pre { white-space: pre-wrap; word-break: break-all; margin: 0; font-family: monospace; color: #e1e1e6; }
   </style>
</head>
<body>
   <div class="container">
       
       <!-- Top bar containing Auth and Control Panel buttons -->
       <div class="header-bar">
           <div>
               <button id="ctrl_panel_btn" class="btn" style="display: none;" onclick="toggleModal('admin_modal', true)">⚙️ Панель управления</button>
           </div>
           <h1>Мониторинг Контрактов</h1>
           <div>
               <button id="auth_btn" class="btn btn-secondary" onclick="openAuthAction()">Войти</button>
           </div>
       </div>

       <div class="param">Статус системы: <span id="status">Загрузка...</span></div>
       <div class="param">Время сервера (КВ/МСК): <span id="time" class="value">00:00:00</span></div>

       <div class="next-box">
           <div class="next-title">СЛЕДУЮЩИЙ КОНТРАКТ: <span id="next_skipped_badge" class="skipped-badge" style="display: none;">ПРОПУЩЕН</span></div>
           <div id="next_text" style="font-weight: bold; color: #f5c2e7; white-space: pre-wrap;">Загрузка...</div>
           <div style="margin-top: 5px; font-size: 14px;">Отправка через: <span id="next_time" style="color: #a6e3a1; font-weight: bold;">--</span></div>
           <div style="margin-top: 5px; font-size: 14px;">Срок контракта: <span id="contract_expiry" style="color: #f9e2af;">--</span> <span id="next_alert" style="color: #f75a68; font-weight: bold;"></span></div>
       </div>

       <h2>📋 Все активные контракты</h2>
       <table>
           <thead>
               <tr>
                   <th style="width: 20%;">Время</th>
                   <th style="width: 60%;">Текст контракта</th>
                   <th style="width: 20%;">Срок действия</th>
               </tr>
           </thead>
           <tbody id="contracts_table_body">
               <tr><td colspan="3" style="text-align: center;">Загрузка списка...</td></tr>
           </tbody>
       </table>
   </div>

   <!-- Auth Modal overlay -->
   <div id="auth_modal" class="modal-overlay">
       <div class="modal-box">
           <h3>Авторизация</h3>
           <p style="color: #a8a8b3; font-size: 14px; margin-bottom: 20px;">Введите секретный пароль администратора</p>
           <div id="auth_error" style="color: #f75a68; font-weight: bold; margin-bottom: 12px; display: none;">Неверный пароль</div>
           <input type="password" id="admin_password_input" placeholder="Пароль" required>
           <div style="display: flex; gap: 10px;">
               <button class="btn" style="flex: 1; justify-content: center;" onclick="submitAuth()">Войти</button>
               <button class="btn btn-secondary" style="flex: 1; justify-content: center;" onclick="toggleModal('auth_modal', false)">Отмена</button>
           </div>
       </div>
   </div>

   <!-- Admin Control Panel Modal overlay -->
   <div id="admin_modal" class="modal-overlay">
       <div class="modal-box" style="max-width: 440px;">
           <h3>Панель управления</h3>
           <p style="color: #a8a8b3; font-size: 14px; margin-bottom: 20px;">Выберите необходимое административное действие</p>
           
           <div class="modal-buttons">
               <button id="modal_pause_btn" class="btn" style="justify-content: center; padding: 12px;" onclick="triggerPause()"></button>
               <button id="modal_skip_btn" class="btn btn-skip" style="justify-content: center; padding: 12px;" onclick="triggerSkip()"></button>
               <a href="https://docs.google.com/spreadsheets/d/1B8Ts_DHQ11878tw1Qa8mUdjxFdCb249v78R10n9czBw/edit?gid=0#gid=0" target="_blank" class="btn btn-link" style="justify-content: center; padding: 12px; text-decoration: none;">📋 Открыть Google Таблицу</a>
               <button class="btn btn-secondary" style="justify-content: center; padding: 12px; margin-top: 10px;" onclick="toggleModal('admin_modal', false)">Закрыть панель</button>
           </div>
       </div>
   </div>

   <script>
       let isAuthorized = false;
       let nextIsSkipped = false;

       function toggleModal(id, show) {
           const modal = document.getElementById(id);
           if (show) {
               modal.classList.add('show');
               if (id === 'auth_modal') {
                   document.getElementById('admin_password_input').focus();
                   document.getElementById('auth_error').style.display = 'none';
                   document.getElementById('admin_password_input').value = '';
               }
           } else {
               modal.classList.remove('show');
           }
       }

       async function openAuthAction() {
           if (isAuthorized) {
               // Logout action
               try {
                   await fetch('/api/logout', { method: 'POST' });
                   isAuthorized = false;
                   updateStats();
               } catch (e) { console.error(e); }
           } else {
               toggleModal('auth_modal', true);
           }
       }

       async function submitAuth() {
           const password = document.getElementById('admin_password_input').value;
           const errorBlock = document.getElementById('auth_error');
           try {
               const res = await fetch('/api/login', {
                   method: 'POST',
                   headers: { 'Content-Type': 'application/json' },
                   body: JSON.stringify({ password })
               });
               if (res.ok) {
                   isAuthorized = true;
                   toggleModal('auth_modal', false);
                   updateStats();
               } else {
                   errorBlock.style.display = 'block';
               }
           } catch(e) {
               errorBlock.innerText = 'Ошибка подключения к серверу';
               errorBlock.style.display = 'block';
           }
       }

       async function triggerPause() {
           try {
               await fetch('/api/toggle', { method: 'POST' });
               updateStats();
           } catch(e) { console.error(e); }
       }

       async function triggerSkip() {
           try {
               await fetch('/api/skip_next', { method: 'POST' });
               updateStats();
           } catch(e) { console.error(e); }
       }

       async function updateStats() {
           try {
               let res = await fetch('/api/stats');
               let data = await res.json();
               
               isAuthorized = data.is_authorized;
               nextIsSkipped = data.is_next_skipped;
               
               // Render Auth Buttons
               const authBtn = document.getElementById('auth_btn');
               const ctrlBtn = document.getElementById('ctrl_panel_btn');
               if (isAuthorized) {
                   authBtn.innerText = 'Выйти';
                   authBtn.className = 'btn btn-secondary';
                   ctrlBtn.style.display = 'inline-flex';
               } else {
                   authBtn.innerText = 'Войти';
                   authBtn.className = 'btn';
                   ctrlBtn.style.display = 'none';
               }

               // System status styling
               let statusElem = document.getElementById('status');
               let modalPauseBtn = document.getElementById('modal_pause_btn');
               
               if (data.is_enabled) {
                   statusElem.innerText = "РАБОТАЕТ ЧЕРЕЗ ВЕБХУК";
                   statusElem.className = "status-on";
                   modalPauseBtn.innerText = "⏸ Поставить рассылку на паузу";
                   modalPauseBtn.className = "btn btn-pause";
               } else {
                   statusElem.innerText = "НА ПАУЗЕ";
                   statusElem.className = "status-off";
                   modalPauseBtn.innerText = "▶️ Запустить рассылку";
                   modalPauseBtn.className = "btn";
               }

               // Next skipped button dynamic labeling
               const modalSkipBtn = document.getElementById('modal_skip_btn');
               if (nextIsSkipped) {
                   modalSkipBtn.innerText = "🔄 Отменить пропуск контракта";
                   document.getElementById('next_skipped_badge').style.display = 'inline-block';
               } else {
                   modalSkipBtn.innerText = "⏭ Пропустить следующий контракт";
                   document.getElementById('next_skipped_badge').style.display = 'none';
               }

               document.getElementById('next_text').innerText = data.next_msg;
               document.getElementById('next_time').innerText = data.next_time_left;
               document.getElementById('contract_expiry').innerText = data.contract_expiry || "Не указан";
               document.getElementById('next_alert').innerText = data.next_is_last ? "⚠️ ПОСЛЕДНИЙ ДЕНЬ!" : "";

               // Contracts Table renderer
               let tableBody = document.getElementById('contracts_table_body');
               tableBody.innerHTML = "";
               if (data.all_contracts && data.all_contracts.length > 0) {
                   data.all_contracts.forEach(c => {
                       let row = document.createElement('tr');
                       let warn = c.is_last_day ? '<span class="alert-expiry">⚠️ ПОСЛЕДНИЙ ДЕНЬ</span>' : '';
                       let isSkippedBadge = c.is_skipped ? ' <span class="skipped-badge" style="font-size: 10px; padding: 1px 4px; vertical-align: middle;">ПРОПУЩЕН</span>' : '';
                       row.innerHTML = `
                           <td class="td-time">${c.time}${isSkippedBadge}</td>
                           <td><pre>${c.text}</pre></td>
                           <td class="td-expiry">${c.expiry}${warn}</td>
                       `;
                       tableBody.appendChild(row);
                   });
               } else {
                   tableBody.innerHTML = `<tr><td colspan="3" style="text-align: center;">Таблица пуста</td></tr>`;
               }
           } catch(e) { }
       }

       // Time sync ticks
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

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    password = data.get('password')
    if password == ADMIN_PASSWORD:
        session['is_authorized'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Неверный пароль"}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/toggle', methods=['POST'])
def toggle_status():
    if not session.get('is_authorized'):
        return jsonify({"error": "Unauthorized"}), 401
    global is_bot_enabled
    is_bot_enabled = not is_bot_enabled
    return jsonify({"success": True, "is_enabled": is_bot_enabled})

@app.route('/api/skip_next', methods=['POST'])
def skip_next():
    if not session.get('is_authorized'):
        return jsonify({"error": "Unauthorized"}), 401
    global skipped_times
    next_time = get_next_execution_time()
    if next_time:
        if next_time in skipped_times:
            skipped_times.remove(next_time)
            print(f"[LOG] Пропуск на время {next_time} отменен пользователем.")
            return jsonify({"success": True, "action": "unskipped", "time": next_time})
        else:
            skipped_times.add(next_time)
            print(f"[LOG] Добавлен пропуск для следующего контракта на время {next_time}.")
            return jsonify({"success": True, "action": "skipped", "time": next_time})
    return jsonify({"success": False, "error": "Нет запланированных контрактов для пропуска"})

@app.route('/api/stats')
def get_stats():
    next_msg, next_time_left, contract_expiry, next_is_last = get_next_message_info()
    
    # Определяем, пропущено ли следующее по расписанию время
    next_exec_time = get_next_execution_time()
    is_next_skipped = (next_exec_time in skipped_times) if next_exec_time else False
    
    # Получаем все контракты и проверяем их статус пропуска
    all_contracts = get_all_contracts_from_sheet()
    for c in all_contracts:
        times = c['time'].split()
        c['is_skipped'] = any(parse_time(t) in skipped_times for t in times if parse_time(t))
        
    return jsonify({
        "is_authorized": bool(session.get('is_authorized')),
        "is_enabled": is_bot_enabled,
        "next_msg": next_msg,
        "next_time_left": next_time_left,
        "contract_expiry": contract_expiry,
        "next_is_last": next_is_last,
        "is_next_skipped": is_next_skipped,
        "all_contracts": all_contracts
    })

if __name__ == '__main__':
    # Принудительно греем кэш при старте
    fetch_sheet_rows()
    threading.Thread(target=cron_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
