import os
import openai
import gspread
import json  # Для загрузки JSON из переменных окружения
import re
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Глобальный словарь для хранения истории переписки с каждым пользователем
conversation_histories = {}

# Инициализация доступа к Google Sheets (теперь без загрузки файла!)
def init_gsheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]

    # Читаем JSON-ключ из переменных окружения (Replit Secrets)
    google_creds = os.environ.get("GOOGLE_CLOUD_CREDENTIALS")

    if not google_creds:
        raise ValueError("Ошибка: Ключ Google Cloud не найден в переменных окружения!")

    creds_dict = json.loads(google_creds)  # Преобразуем JSON-строку в Python-словарь
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("SupplementsTable").sheet1
    return sheet

sheet = init_gsheet()

# Функция для получения актуальной справочной информации
def get_table_reference_info():
    try:
        records = sheet.get_all_records()
    except Exception as e:
        return {}

    info_dict = {}
    for record in records:
        supplement = record.get("supplement", "").strip().lower()
        symptom = record.get("symptom", "Не указано")
        dosage = record.get("dosage", "Не указано")
        compound = record.get("compaund", "Нет информации")
        ecomlink = record.get("ecomlink", "").strip()

        info_dict[supplement] = {
            "symptom": symptom,
            "dosage": dosage,
            "compound": compound,
            "ecomlink": ecomlink
        }

    return info_dict

# Настройка API-ключей
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Создаем экземпляр OpenAI API-клиента
client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

# Функция для формирования актуального системного промпта
def get_system_prompt():
    supplement_info = get_table_reference_info()
    formatted_info = "\n".join([
        f"Симптом: {info['symptom']} | БАД: {supplement} | Дозировка: {info['dosage']} | Состав: {info['compound']}"
        for supplement, info in supplement_info.items()
    ])

    return f"""Ты — эксперт-консультант по здоровью и нутрицевтике.
Твоя задача – помочь клиенту e-commerce магазина подобрать подходящий пептидный комплекс на основе его индивидуальных запросов.  
Ты должен задавать уточняющие вопросы, анализировать ответы и предлагать персонализированные рекомендации, учитывая ассортимент магазина.
**Шаг 1: Сбор информации у клиента**  
Прежде чем давать рекомендации, задай клиенту уточняющие вопросы:  
1. **Возраст и пол:** (например, «Мне важно понимать ваш возраст и пол, так как это влияет на подбор БАДов»)  
2. **Основные жалобы или цели:** (например, «С чем вы хотите работать? Это может быть энергия, восстановление после нагрузок, поддержка сердца, ЖКТ, либидо и т. д.»)  
3. **Образ жизни:** (например, «Вы ведете активный или сидячий образ жизни? Есть ли повышенные физические или стрессовые нагрузки?»)  
4. **Хронические заболевания и аллергии:** (например, «Есть ли у вас хронические заболевания, аллергии или особенности, которые стоит учитывать?»)  
5. **Предпочтения по приему:** (например, «В каком формате вам удобнее принимать БАДы? Капсулы, порошки, капли?»)  

**Шаг 2: Формирование рекомендаций на основе ассортимента**

Используй следующую информацию о БАдах, чтобы давать рекомендации:

{formatted_info}

Если в ответе упоминается БАД, НЕ выдумывай ссылку, а добавляй её только если она есть в таблице.

**Шаг 3: Дополнительные рекомендации**  
- Подскажи клиенту, какие изменения в образе жизни и питании помогут усилить эффект БАДов.  
- Например, при проблемах со сном посоветуй избегать кофеина вечером, а при проблемах с суставами – увеличить потребление коллагена и Омега-3.
**Шаг 4: Ограничения и предостережения**  
- Если клиент указывает противопоказания (беременность, хронические болезни) – уточни, прежде чем рекомендовать.  
- Не ставь диагнозы и не обещай излечения, формулируй рекомендации мягко:  
  **"Этот комплекс может поддерживать здоровье суставов и снизить дискомфорт"**  
  И для примера не говори прямо **"Этот комплекс избавит вас от боли в суставах"**  
- Упомяни, что перед началом приема БАДов рекомендуется консультация с врачом.
**Формат ответа:**  
Ответ должен быть четким, понятным и без сложных медицинских терминов. Используй структуру:  

**Ваши данные:**  
(краткое повторение ключевых пунктов, которые дал пользователь)  

**Рекомендуемые пептидные комплексы:**  
1. **Название БАД** – краткое описание, почему он вам подходит.  
   - Как принимать: ...  
2. **Название БАД** – краткое описание, почему он вам подходит.  
   - Как принимать: ...  

**Дополнительные рекомендации:**  
- Что можно улучшить в образе жизни  
- Какие продукты добавить в рацион  

**Важно:**  
- Перед началом приема проконсультируйтесь с врачом, если у вас есть хронические заболевания или вы принимаете лекарства.  

"""

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    conversation_histories[user_id] = [{"role": "system", "content": get_system_prompt()}]
    await update.message.reply_text("Привет! Расскажите о ваших жалобах и симптомах, чтобы я мог помочь.")

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    if user_id not in conversation_histories:
        conversation_histories[user_id] = [{"role": "system", "content": get_system_prompt()}]

    supplement_info = get_table_reference_info()

    conversation_histories[user_id][0]["content"] = get_system_prompt()
    conversation_histories[user_id].append({"role": "user", "content": user_text})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=conversation_histories[user_id],
            temperature=0.7
        )
        chat_reply = response.choices[0].message.content

        added_links = set()
        for supplement, info in supplement_info.items():
            pattern = r"\b" + re.escape(supplement) + r"\b"
            if re.search(pattern, chat_reply, re.IGNORECASE):
                ecomlink = info.get("ecomlink")
                if ecomlink and ecomlink not in added_links:
                    chat_reply += f"\n\n💡 Вы можете ознакомиться с продуктом здесь: {ecomlink} 🔗"
                    added_links.add(ecomlink)

        conversation_histories[user_id].append({"role": "assistant", "content": chat_reply})

    except Exception as e:
        chat_reply = f"Ошибка при получении ответа от ChatGPT: {str(e)}"

    await update.message.reply_text(chat_reply)

# Запуск бота
def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
