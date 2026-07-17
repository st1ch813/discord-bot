import os
import re
import csv
import json
import asyncio
import logging
from datetime import datetime, timedelta
import threading
import requests
from flask import Flask, render_template_string, jsonify, request, session, redirect

# ================= НАСТРОЙКИ БОТА =================
ROLE_ID = "1447219553259094219"
# Тщательно очищаем ID от любых невидимых символов, кавычек и пробелов
SHEET_ID = "1B8Ts_DHQ11878tw1Qa8mUdjxFdCb249v78R10n9czBw".strip().replace("'", "").replace('"', "").replace(" ", "")
# ==================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-key-12345")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "WN063")

system_state = {
    "is_paused": False,
    "paused_contracts": []  # Список кодовых названий контрактов, которые сейчас приостановлены
}

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

def format_money(value):
    return f"{value:,.0f} $".replace(",", " ")

def get_msk_time():
    return datetime.utcnow() + timedelta(hours=3)

def parse_database():
    contracts = []
    clean_sheet_id = SHEET_ID.strip().replace("'", "").replace('"', "").replace(" ", "")
    export_url = f"https://docs.google.com/spreadsheets/d/{clean_sheet_id}/export?format=csv&gid=0".strip()
    now = get_msk_time()
    
    try:
        logger.info(f"Запрос к Google Таблице по адресу: '{export_url}'")
        response = requests.get(export_url, timeout=10)
        if response.status_code != 200:
            logger.error(f"Не удалось скачать Google Таблицу. Статус: {response.status_code}")
            return contracts
            
        csv_data = response.content.decode('utf-8').splitlines()
        reader = csv.reader(csv_data)
        
        for row in reader:
            if len(row) < 3:
                continue
            times_str, text, date_range = row[0], row[1], row[2]
            
            # Читаем четвертую колонку (кодовое имя). Если ее нет или она пустая — пишем "Без названия"
            contract_code = row[3].strip() if len(row) > 3 and row[3].strip() else "Без названия"
            
            if "время" in times_str.lower() or "текст" in text.lower():
                continue
                
            clean_text = text.strip().replace('`', '').strip('"').strip()
            times = [t.strip() for t in times_str.split() if t.strip()]
            
            if times and clean_text:
                date_status = "active" 
                try:
                    dates = date_range.split('-')
                    if len(dates) == 2:
                        end_str = dates[1].strip()
                        current_year = now.year
                        
                        end_date = datetime.strptime(f"{end_str}.{current_year}", "%d.%m.%Y").date()
                        today = now.date()
                        
                        if today > end_date:
                            date_status = "expired"
                        elif today == end_date:
                            date_status = "last_day"
                except Exception:
                    pass

                contracts.append({
                    "times": times,
                    "text": clean_text,
                    "date_range": date_range.strip(),
                    "date_status": date_status,
                    "code": contract_code  # Сохраняем код контракта в базу
                })
    except Exception as e:
        logger.error(f"Ошибка при импорте/парсинге Google Таблицы: {e}")
    
    return contracts

def get_next_contract_info():
    now = get_msk_time()
    contracts = parse_database()
    upcoming_contracts = []
    
    for contract in contracts:
        if contract["date_status"] == "expired":
            continue
            
        try:
            dates = contract["date_range"].split('-')
            if len(dates) == 2:
                start_str, end_str = dates[0].strip(), dates[1].strip()
                current_year = now.year
                
                start_date = datetime.strptime(f"{start_str}.{current_year}", "%d.%m.%Y")
                end_date = datetime.strptime(f"{end_str}.{current_year}", "%d.%m.%Y") + timedelta(days=1)
                
                if not (start_date <= now <= end_date):
                    continue
        except Exception:
            pass
            
        for t_str in contract["times"]:
            try:
                t_time = datetime.strptime(t_str, "%H:%M").time()
                t_datetime = datetime.combine(now.date(), t_time)
                
                if t_datetime < now:
                    t_datetime += timedelta(days=1)
                
                # Проверяем, на паузе ли конкретно этот контракт по его кодовому названию
                is_skipped = (contract["code"] != "Без названия" and contract["code"] in system_state["paused_contracts"])
                
                upcoming_contracts.append({
                    "datetime": t_datetime,
                    "time_str": t_str,
                    "text": contract["text"],
                    "date_range": contract["date_range"],
                    "is_skipped": is_skipped,
                    "code": contract["code"]
                })
            except Exception as e:
                logger.error(f"Ошибка парсинга времени {t_str}: {e}")

    if not upcoming_contracts:
        return None

    upcoming_contracts.sort(key=lambda x: x["datetime"])
    return upcoming_contracts[0]

# --- FLASK WEBSERVER ---

@app.route('/')
def dashboard():
    html_template = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Управление Рассылкой & Калькулятор</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            body { background-color: #0f0a0a; color: #e5e5e5; font-family: sans-serif; }
            .glow-card { box-shadow: 0 4px 20px rgba(220, 38, 38, 0.15); border: 1px solid rgba(220, 38, 38, 0.2); }
            .tab-active { border-bottom: 2px solid #ef4444; color: #ef4444; }
        </style>
    </head>
    <body class="min-h-screen flex flex-col pb-10">

        <header class="bg-[#1a1313] border-b border-red-900/40 p-4 sticky top-0 z-50 shadow-lg">
            <div class="max-w-6xl mx-auto flex justify-between items-center">
                <div class="flex items-center space-x-6">
                    <h1 class="text-xl font-bold text-red-500 flex items-center space-x-2">
                        <i class="fa-solid fa-file-invoice-dollar"></i>
                        <span>Secretary Alice</span>
                    </h1>
                    
                    <nav class="hidden md:flex space-x-4">
                        <button onclick="switchTab('monitoring')" id="tab-monitoring" class="py-1 px-3 text-sm font-semibold transition tab-active">
                            Мониторинг
                        </button>
                        <button onclick="switchTab('calculator')" id="tab-calculator" class="py-1 px-3 text-sm font-semibold text-gray-400 hover:text-white transition">
                            Калькулятор
                        </button>
                    </nav>

                    {% if session.get('authorized') %}
                    <button onclick="openControlModal()" class="bg-red-600 hover:bg-red-700 text-white font-semibold py-1.5 px-4 rounded text-xs transition shadow flex items-center space-x-1.5">
                        <i class="fa-solid fa-sliders"></i>
                        <span>Управление паузами</span>
                    </button>
                    {% endif %}
                </div>

                <div class="flex items-center space-x-4">
                    {% if session.get('authorized') %}
                    <span class="text-xs text-green-400 flex items-center space-x-1">
                        <span class="h-2 w-2 rounded-full bg-green-500 animate-pulse"></span>
                        <span>Администратор</span>
                    </span>
                    <a href="/logout" class="text-xs text-gray-400 hover:text-red-400 transition">Выйти</a>
                    {% else %}
                    <button onclick="openLoginModal()" class="bg-[#2a1d1d] hover:bg-[#3d2a2a] border border-red-900/60 text-red-400 font-semibold py-1.5 px-4 rounded text-xs transition">
                        Войти
                    </button>
                    {% endif %}
                </div>
            </div>
        </header>

        <main class="max-w-6xl w-full mx-auto px-4 mt-8 flex-grow">
            
            <div id="section-monitoring" class="space-y-6">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="bg-[#181111] glow-card rounded-lg p-5 flex items-center justify-between">
                        <div>
                            <p class="text-gray-400 text-xs uppercase">Общий статус</p>
                            <p id="system-status-text" class="text-lg font-bold">РАБОТАЕТ</p>
                        </div>
                    </div>
                    <div class="bg-[#181111] glow-card rounded-lg p-5 flex items-center justify-between">
                        <div>
                            <p class="text-gray-400 text-xs uppercase">Время МСК</p>
                            <p id="server-time" class="text-lg font-bold text-red-400">...</p>
                        </div>
                    </div>
                    <div class="bg-[#181111] glow-card rounded-lg p-5 flex items-center justify-between">
                        <div>
                            <p class="text-gray-400 text-xs uppercase">Всего контрактов</p>
                            <p id="total-contracts-count" class="text-lg font-bold text-white">...</p>
                        </div>
                    </div>
                </div>

                <div class="bg-[#181111] glow-card rounded-lg p-6">
                    <h2 class="text-xs uppercase font-bold text-gray-400 mb-3">Следующий контракт</h2>
                    <div id="next-contract-container" class="space-y-4">
                        <div class="text-center py-6 text-gray-500">Загрузка...</div>
                    </div>
                </div>

                <div class="bg-[#181111] glow-card rounded-lg p-6">
                    <h2 class="text-md font-bold text-white mb-4">Все active-контракты</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse table-auto">
                            <thead>
                                <tr class="border-b border-red-900/40 text-gray-400 text-xs uppercase">
                                    <th class="py-3 px-4 w-[150px]">Код</th>
                                    <th class="py-3 px-4 w-[220px]">Время</th>
                                    <th class="py-3 px-4 w-full">Текст контракта</th>
                                    <th class="py-3 px-4 whitespace-nowrap">Срок действия</th>
                                    <th class="py-3 px-4 text-center whitespace-nowrap w-[150px]">Статус</th>
                                </tr>
                            </thead>
                            <tbody id="contracts-table-body" class="divide-y divide-red-900/20 text-sm">
                                <tr><td colspan="5" class="text-center py-8 text-gray-500">Загрузка...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div id="section-calculator" class="hidden space-y-6">
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div class="lg:col-span-2 bg-[#181111] glow-card rounded-lg p-6 space-y-4">
                        <h2 class="text-lg font-bold text-white">Параметры контракта</h2>
                        <div>
                            <label class="block text-xs uppercase text-gray-400 mb-2">Текст</label>
                            <textarea id="calc-text" rows="8" placeholder="Вставьте текст контракта..." 
                                      class="w-full bg-[#100b0b] border border-red-950 rounded-lg p-3 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-red-500 resize-none"
                                      oninput="calculateContract()"></textarea>
                        </div>
                        
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                            <div>
                                <label class="block text-xs uppercase text-gray-400 mb-2">Тип объявления</label>
                                <div class="grid grid-cols-1 gap-2">
                                    <button onclick="setContractType('green')" id="btn-type-green" class="py-2 px-3 rounded-lg border border-red-900/60 font-semibold text-xs bg-red-950/40 text-red-400 transition">
                                        Зеленый (300$)
                                    </button>
                                    <button onclick="setContractType('sms')" id="btn-type-sms" class="py-2 px-3 rounded-lg border border-gray-800 font-semibold text-xs text-gray-400 transition">
                                        SMS (200$)
                                    </button>
                                </div>
                            </div>
                            <div>
                                <label class="block text-xs uppercase text-gray-400 mb-2">Сообщений в день</label>
                                <div class="flex items-center h-[42px] bg-[#100b0b] border border-red-950 rounded-lg overflow-hidden">
                                    <button onclick="adjustCount('calc-msg-per-day', -1)" class="w-10 h-full text-gray-400 hover:text-white font-bold text-base">-</button>
                                    <input type="number" id="calc-msg-per-day" value="1" min="1" oninput="calculateContract()" class="flex-grow bg-transparent text-center text-sm font-bold text-white focus:outline-none">
                                    <button onclick="adjustCount('calc-msg-per-day', 1)" class="w-10 h-full text-gray-400 hover:text-white font-bold text-base">+</button>
                                </div>
                            </div>
                            <div>
                                <label class="block text-xs uppercase text-gray-400 mb-2">Количество дней</label>
                                <div class="flex items-center h-[42px] bg-[#100b0b] border border-red-950 rounded-lg overflow-hidden">
                                    <button onclick="adjustCount('calc-days', -1)" class="w-10 h-full text-gray-400 hover:text-white font-bold text-base">-</button>
                                    <input type="number" id="calc-days" value="7" min="1" oninput="calculateContract()" class="flex-grow bg-transparent text-center text-sm font-bold text-white focus:outline-none">
                                    <button onclick="adjustCount('calc-days', 1)" class="w-10 h-full text-gray-400 hover:text-white font-bold text-base">+</button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="bg-[#181111] glow-card rounded-lg p-6 flex flex-col justify-between">
                        <div class="space-y-4">
                            <h2 class="text-lg font-bold text-white">Результаты расчета</h2>
                            <div class="bg-[#100b0b] p-3 rounded-lg border border-red-950 text-xs space-y-1 text-gray-400">
                                <div class="flex justify-between"><span>Всего символов:</span><span id="res-total-chars" class="text-white">0</span></div>
                                <div class="flex justify-between"><span>За 1 выход:</span><span id="res-one-day-sum" class="text-white">0 $</span></div>
                            </div>
                            <div class="space-y-2">
                                <div class="bg-red-950/20 border border-red-900/40 p-3 rounded-lg">
                                    <p class="text-gray-400 text-[10px] uppercase">Общая стоимость</p>
                                    <p id="res-total-sum" class="text-2xl font-black text-red-500">0 $</p>
                                </div>
                                <div class="bg-blue-950/10 border border-blue-900/30 p-3 rounded-lg">
                                    <p class="text-gray-400 text-[10px] uppercase flex justify-between"><span>В казну</span><span>75%</span></p>
                                    <p id="res-treasury-sum" class="text-lg font-bold text-blue-400">0 $</p>
                                </div>
                                <div class="bg-emerald-950/10 border border-emerald-900/30 p-3 rounded-lg">
                                    <p class="text-gray-400 text-[10px] uppercase flex justify-between"><span>Сотруднику</span><span>25%</span></p>
                                    <p id="res-employee-sum" class="text-lg font-bold text-emerald-400">0 $</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>

        <div id="login-modal" class="hidden fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4">
            <div class="bg-[#181111] border border-red-900/60 rounded-xl max-w-sm w-full p-6 space-y-4">
                <div class="flex justify-between items-center">
                    <h3 class="text-white font-bold">Авторизация</h3>
                    <button onclick="closeLoginModal()" class="text-gray-500 hover:text-white">&times;</button>
                </div>
                <form action="/login" method="POST" class="space-y-3">
                    <input type="password" name="password" required placeholder="Пароль..." class="w-full bg-[#100b0b] border border-red-950 rounded p-2 text-sm text-white focus:outline-none">
                    <button type="submit" class="w-full bg-red-600 text-white font-bold py-2 rounded text-sm">Войти</button>
                </form>
            </div>
        </div>

        <div id="control-modal" class="hidden fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4">
            <div class="bg-[#181111] border border-red-900/60 rounded-xl max-w-md w-full p-6 space-y-4">
                <div class="flex justify-between items-center">
                    <h3 class="text-white font-bold">Управление контрактами</h3>
                    <button onclick="closeControlModal()" class="text-gray-500 hover:text-white">&times;</button>
                </div>
                
                <div class="space-y-4">
                    <div>
                        <p class="text-xs text-gray-400 uppercase mb-2">Глобальное состояние</p>
                        <button id="ctrl-btn-pause" onclick="togglePause()" class="w-full text-white font-bold py-2 px-4 rounded-lg text-sm flex justify-between items-center shadow">
                            <span>Общая пауза</span><span id="ctrl-pause-status">...</span>
                        </button>
                    </div>

                    <div>
                        <p class="text-xs text-gray-400 uppercase mb-2">Приостановка по кодовому названию</p>
                        <div id="paused-contracts-list" class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                            <p class="text-xs text-gray-500">Загрузка контрактов...</p>
                        </div>
                    </div>

                    <a href="https://docs.google.com/spreadsheets/d/{{ sheet_id }}/edit?gid=0#gid=0" target="_blank" class="w-full bg-[#1b221d] text-emerald-400 font-bold py-2.5 px-4 rounded-lg text-sm flex justify-between items-center text-center">
                        <span>Открыть Google Таблицу</span><i class="fa-solid fa-up-right-from-square"></i>
                    </a>
                </div>
            </div>
        </div>

        <script>
            let currentTab = 'monitoring';
            let contractRate = 300; 

            function switchTab(tabName) {
                currentTab = tabName;
                const tabMon = document.getElementById('tab-monitoring');
                const tabCalc = document.getElementById('tab-calculator');
                const secMon = document.getElementById('section-monitoring');
                const secCalc = document.getElementById('section-calculator');

                if (tabName === 'monitoring') {
                    tabMon.className = "py-1 px-3 text-sm font-semibold transition tab-active";
                    tabCalc.className = "py-1 px-3 text-sm font-semibold text-gray-400 hover:text-white transition";
                    secMon.classList.remove('hidden');
                    secCalc.classList.add('hidden');
                } else {
                    tabMon.className = "py-1 px-3 text-sm font-semibold text-gray-400 hover:text-white transition";
                    tabCalc.className = "py-1 px-3 text-sm font-semibold transition tab-active";
                    secMon.classList.add('hidden');
                    secCalc.classList.remove('hidden');
                }
            }

            function openLoginModal() { document.getElementById('login-modal').classList.remove('hidden'); }
            function closeLoginModal() { document.getElementById('login-modal').classList.add('hidden'); }
            function openControlModal() { document.getElementById('control-modal').classList.remove('hidden'); }
            function closeControlModal() { document.getElementById('control-modal').classList.add('hidden'); }

            function setContractType(type) {
                contractRate = (type === 'green') ? 300 : 200; 
                document.getElementById('btn-type-green').className = type === 'green' ? "py-2 px-3 rounded-lg border border-red-900/60 font-semibold text-xs bg-red-950/40 text-red-400" : "py-2 px-3 rounded-lg border border-gray-800 font-semibold text-xs text-gray-400";
                document.getElementById('btn-type-sms').className = type === 'sms' ? "py-2 px-3 rounded-lg border border-red-900/60 font-semibold text-xs bg-red-950/40 text-red-400" : "py-2 px-3 rounded-lg border border-gray-800 font-semibold text-xs text-gray-400";
                calculateContract();
            }

            function adjustCount(inputId, amount) {
                const input = document.getElementById(inputId);
                let val = (parseInt(input.value) || 1) + amount;
                input.value = val < 1 ? 1 : val;
                calculateContract();
            }

            function calculateContract() {
                const text = document.getElementById('calc-text').value;
                const msgPerDay = parseInt(document.getElementById('calc-msg-per-day').value) || 1;
                const days = parseInt(document.getElementById('calc-days').value) || 1;

                let calcLength = text.length;

                const oneMsgSum = calcLength * contractRate;
                const totalSum = oneMsgSum * msgPerDay * days;
                const treasurySum = totalSum * 0.75;
                const employeeSum = totalSum * 0.25;

                document.getElementById('res-total-chars').innerText = calcLength;
                document.getElementById('res-one-day-sum').innerText = oneMsgSum.toLocaleString() + ' $';
                document.getElementById('res-total-sum').innerText = totalSum.toLocaleString() + ' $';
                document.getElementById('res-treasury-sum').innerText = treasurySum.toLocaleString() + ' $';
                document.getElementById('res-employee-sum').innerText = employeeSum.toLocaleString() + ' $';
            }

            async function toggleContractPause(contractCode) {
                await fetch('/api/toggle-contract-pause', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: contractCode })
                });
                updateStats();
            }

            async function updateStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('server-time').innerText = data.server_time;
                    document.getElementById('total-contracts-count').innerText = data.total_contracts;
                    
                    // Общий статус системы
                    const sysStatusText = document.getElementById('system-status-text');
                    if (data.is_paused) {
                        sysStatusText.className = "text-lg font-bold text-red-500";
                        sysStatusText.innerText = "НА ПАУЗЕ";
                    } else {
                        sysStatusText.className = "text-lg font-bold text-green-400";
                        sysStatusText.innerText = "РАБОТАЕТ";
                    }

                    const btnPause = document.getElementById('ctrl-btn-pause');
                    const statPause = document.getElementById('ctrl-pause-status');
                    if (btnPause && statPause) {
                        if (data.is_paused) {
                            btnPause.className = "w-full bg-emerald-600 text-white font-bold py-2 px-4 rounded-lg text-sm flex justify-between items-center";
                            statPause.innerText = "ВКЛЮЧИТЬ";
                        } else {
                            btnPause.className = "w-full bg-red-600 text-white font-bold py-2 px-4 rounded-lg text-sm flex justify-between items-center";
                            statPause.innerText = "ПАУЗА";
                        }
                    }

                    // Список паузы в модалке (только уникальные коды контрактов, исключая "Без названия")
                    const uniqueCodes = [...new Set(data.all_contracts.map(c => c.code))].filter(code => code && code !== "Без названия");
                    const pausedListContainer = document.getElementById('paused-contracts-list');
                    if (pausedListContainer) {
                        if (uniqueCodes.length > 0) {
                            pausedListContainer.innerHTML = uniqueCodes.map(code => {
                                const isChecked = data.paused_contracts.includes(code);
                                return `
                                    <label class="flex items-center justify-between bg-[#100b0b] p-2 rounded border border-red-950/40 cursor-pointer select-none">
                                        <span class="text-xs text-gray-300 font-semibold">${code}</span>
                                        <input type="checkbox" onchange="toggleContractPause('${code}')" ${isChecked ? 'checked' : ''} class="w-4 h-4 rounded bg-[#0f0a0a] border-red-900 text-red-600 focus:ring-0">
                                    </label>
                                `;
                            }).join('');
                        } else {
                            pausedListContainer.innerHTML = '<p class="text-xs text-gray-500">Нет именованных контрактов в таблице</p>';
                        }
                    }

                    // Следующий контракт
                    const nextContainer = document.getElementById('next-contract-container');
                    if (data.next_contract) {
                        const nc = data.next_contract;
                        let badge = nc.is_skipped ? '<span class="bg-red-900/60 text-red-300 text-[10px] px-2 py-0.5 rounded whitespace-nowrap">НА ПАУЗЕ</span>' : `<span class="bg-yellow-900/40 text-yellow-500 text-[10px] px-2 py-0.5 rounded whitespace-nowrap">ЧЕРЕЗ ${nc.time_left}</span>`;
                        nextContainer.innerHTML = `
                            <div class="flex justify-between text-xs text-gray-400 border-b border-red-900/10 pb-2">
                                <span>Слот: <strong>${nc.time_str} МСК</strong> (${nc.date_range}) — <i>[${nc.code}]</i></span>${badge}
                            </div>
                            <div class="bg-[#100b0b] p-3 rounded border border-red-950 ${nc.is_skipped ? 'line-through text-gray-500' : 'text-gray-200'} text-sm">${nc.text}</div>
                        `;
                    } else {
                        nextContainer.innerHTML = '<div class="text-center text-gray-500 text-sm">Нет active-контрактов</div>';
                    }

                    // Таблица всех контрактов
                    const tableBody = document.getElementById('contracts-table-body');
                    if (data.all_contracts && data.all_contracts.length > 0) {
                        tableBody.innerHTML = data.all_contracts.map(c => {
                            let statusBadge = '<span class="inline-block bg-green-950/60 text-green-400 border border-green-900/60 text-[10px] font-bold px-2.5 py-1 rounded">Активен</span>';
                            let rowClass = "hover:bg-red-950/5";
                            
                            // Проверяем статус индивидуальной паузы
                            const isIndividualPaused = data.paused_contracts.includes(c.code);
                            
                            if (isIndividualPaused) {
                                statusBadge = '<span class="inline-block bg-yellow-950/60 text-yellow-500 border border-yellow-900/60 text-[10px] font-bold px-2.5 py-1 rounded">Пауза</span>';
                                rowClass = "opacity-60 hover:bg-red-950/5";
                            } else if (c.date_status === 'last_day') {
                                statusBadge = '<span class="inline-block bg-amber-950/60 text-amber-400 border border-amber-900/60 text-[10px] font-bold px-2.5 py-1 rounded text-center leading-tight">Последний<br>день</span>';
                            } else if (c.date_status === 'expired') {
                                statusBadge = '<span class="inline-block bg-red-950/60 text-red-400 border border-red-900/60 text-[10px] font-bold px-2.5 py-1 rounded">Просрочен</span>';
                                rowClass = "opacity-40 hover:bg-red-950/5";
                            }

                            let timeBadges = c.times.map(t => `<span class="inline-block bg-[#261616] text-red-400 border border-red-950 text-xs px-2 py-0.5 rounded font-mono shadow-sm">${t}</span>`).join(' ');

                            return `
                                <tr class="${rowClass}">
                                    <td class="py-3 px-4 font-semibold text-red-400 text-xs break-all">[${c.code}]</td>
                                    <td class="py-3 px-4"><div class="flex flex-wrap gap-1.5 max-w-[210px]">${timeBadges}</div></td>
                                    <td class="py-3 px-4 text-gray-300 break-words max-w-xs md:max-w-xl">${c.text}</td>
                                    <td class="py-3 px-4 text-gray-400 whitespace-nowrap">${c.date_range}</td>
                                    <td class="py-3 px-4 text-center">${statusBadge}</td>
                                </tr>
                            `;
                        }).join('');
                    } else {
                        tableBody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-gray-500">Нет контрактов в базе</td></tr>';
                    }
                } catch (e) {}
            }

            async function togglePause() { await fetch('/api/toggle-pause', { method: 'POST' }); updateStats(); }

            setInterval(updateStats, 2000);
            updateStats();
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, sheet_id=SHEET_ID)

@app.route('/login', methods=['POST'])
def login():
    if request.form.get("password") == ADMIN_PASSWORD:
        session['authorized'] = True
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('authorized', None)
    return redirect('/')

@app.route('/api/stats')
def api_stats():
    now = get_msk_time()
    contracts = parse_database()
    next_c = get_next_contract_info()
    next_contract_data = None
    if next_c:
        diff = next_c["datetime"] - now
        hours, remainder = divmod(int(diff.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_left_str = f"{minutes}м {seconds}с" if hours == 0 else f"{hours}ч {minutes}м"
        next_contract_data = {
            "time_str": next_c["time_str"],
            "text": next_c["text"],
            "date_range": next_c["date_range"],
            "time_left": time_left_str,
            "is_skipped": next_c["is_skipped"],
            "code": next_c["code"]
        }
    return jsonify({
        "server_time": now.strftime("%H:%M:%S"),
        "total_contracts": len(contracts),
        "is_paused": system_state["is_paused"],
        "paused_contracts": system_state["paused_contracts"],
        "next_contract": next_contract_data,
        "all_contracts": contracts
    })

@app.route('/api/toggle-pause', methods=['POST'])
def toggle_pause_api():
    if session.get('authorized'):
        system_state["is_paused"] = not system_state["is_paused"]
    return jsonify({"success": True})

@app.route('/api/toggle-contract-pause', methods=['POST'])
def toggle_contract_pause_api():
    if not session.get('authorized'):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    contract_code = data.get("code")
    
    if contract_code and contract_code != "Без названия":
        if contract_code in system_state["paused_contracts"]:
            system_state["paused_contracts"].remove(contract_code)
        else:
            system_state["paused_contracts"].append(contract_code)
            
    return jsonify({"success": True, "paused_contracts": system_state["paused_contracts"]})

def send_discord_webhook(text):
    if not WEBHOOK_URL: return False
    try:
        full_content = f"<@&{ROLE_ID}>\n```\n{text}\n```"
        requests.post(WEBHOOK_URL, json={"content": full_content}, timeout=10)
        return True
    except: return False

async def schedule_loop():
    last_sent_minute = -1
    while True:
        try:
            now = get_msk_time()
            if now.minute != last_sent_minute:
                current_time_str = now.strftime("%H:%M")
                if not system_state["is_paused"]:
                    for contract in parse_database():
                        if contract["date_status"] == "expired":
                            continue
                        # Если время совпадает
                        if current_time_str in contract["times"]:
                            # Проверяем, не стоит ли данный контракт на индивидуальной паузе
                            if contract["code"] not in system_state["paused_contracts"]:
                                send_discord_webhook(contract["text"])
                last_sent_minute = now.minute
        except: pass
        await asyncio.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, use_reloader=False), daemon=True).start()
    asyncio.run(schedule_loop())
