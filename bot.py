def get_all_contracts_from_sheet():
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID')
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    contracts = []
    try:
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            for row in reader:
                if len(row) < 2: 
                    continue
                    
                time_part = row[0].strip()
                text_part = row[1].strip()
                
                # Пропускаем только пустые строки или заголовок таблицы
                if not time_part or not text_part or "время" in time_part.lower():
                    continue
                
                # Чистим текст от лишних кавычек для отображения на сайте
                clean_text = text_part.replace("```", "").replace("`", "")
                
                expiry_part = row[2].strip() if len(row) >= 3 else ""
                if "срок" in expiry_part.lower() or "годн" in expiry_part.lower():
                    expiry_part = ""
                        
                type_part = row[3].strip() if len(row) >= 4 else "обычное"
                if "тип" in type_part.lower():
                    type_part = "обычное"

                contracts.append({
                    "time": time_part,
                    "text": clean_text,
                    "expiry": expiry_part if expiry_part else "Не указан",
                    "type": type_part,
                    "is_last_day": check_is_last_day(expiry_part)
                })
    except Exception as e:
        print(f"Ошибка получения контрактов: {e}")
    return contracts
