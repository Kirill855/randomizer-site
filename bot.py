import os
import json
import threading
from flask import Flask, jsonify, render_template
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATA_FILE = "messages.json"
lock = threading.Lock()

app = Flask(__name__)

# --- ФУНКЦИИ ХРАНИЛИЩА ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"messages": [], "index": 0}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- ВЕБ-СЕРВЕР ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/next", methods=["POST"])
def next_message():
    with lock:
        data = load_data()
        msgs = data["messages"]
        idx = data["index"]
        if not msgs:
            return jsonify({"message": None, "info": "Список пуст. Отправь сообщения боту."})
        if idx >= len(msgs):
            return jsonify({"message": None, "finished": True, "info": "Сообщения закончились."})
        text = msgs[idx]
        data["index"] = idx + 1
        save_data(data)
        return jsonify({"message": text, "finished": data["index"] >= len(msgs)})

# --- БОТ: КОМАНДЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли текст — он добавится в конец списка.\n\n"
        "Команды:\n"
        "/list — посмотреть и отредактировать список\n"
        "/clear — полностью очистить список"
    )

async def add_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    with lock:
        data = load_data()
        data["messages"].append(text)
        save_data(data)
        count = len(data["messages"])
    await update.message.reply_text(f"✅ Добавлено. Всего сообщений: {count}")

async def clear_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with lock:
        save_data({"messages": [], "index": 0})
    await update.message.reply_text("🗑 Список полностью очищен.")

# --- БОТ: ПРОСМОТР И РЕДАКТИРОВАНИЕ ---
async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    msgs = data["messages"]
    
    if not msgs:
        await update.message.reply_text("Список пуст. Отправь боту текст, чтобы добавить сообщение.")
        return

    text = "📋 **Ваш список сообщений:**\n\n"
    for i, msg in enumerate(msgs):
        # Обрезаем длинные сообщения, чтобы они влезали в кнопку
        short_msg = msg[:15] + "..." if len(msg) > 15 else msg
        text += f"{i+1}. {short_msg}\n"
        
    text += "\nНажмите 🗑 рядом с сообщением, чтобы удалить его."
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=build_keyboard(msgs))

def build_keyboard(msgs):
    keyboard = []
    for i, msg in enumerate(msgs):
        # Кнопка удаления передает индекс сообщения (idx)
        keyboard.append([InlineKeyboardButton(f"🗑 Удалить {i+1}", callback_data=f"del_{i}")])
    return InlineKeyboardMarkup(keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("del_"):
        idx_to_delete = int(data.split("_")[1])
        
        with lock:
            store = load_data()
            msgs = store["messages"]
            
            if 0 <= idx_to_delete < len(msgs):
                deleted_msg = msgs.pop(idx_to_delete)
                # Важно: если мы удаляем сообщение, которое еще не выведено, сдвигаем индекс
                if store["index"] > idx_to_delete:
                    store["index"] -= 1
                save_data(store)
                msgs = store["messages"]
            else:
                await query.edit_message_text("Ошибка: сообщение не найдено.")
                return

        if not msgs:
            await query.edit_message_text("🗑 Все сообщения удалены. Список пуст.")
            return

        # Обновляем текст и кнопки
        text = "📋 **Ваш список сообщений:**\n\n"
        for i, msg in enumerate(msgs):
            short_msg = msg[:15] + "..." if len(msg) > 15 else msg
            text += f"{i+1}. {short_msg}\n"
        text += "\nНажмите 🗑 рядом с сообщением, чтобы удалить его."
        
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=build_keyboard(msgs))

# --- ЗАПУСК БОТА ---
def run_bot():
    if not TOKEN:
        print("ОШИБКА: Токен не задан!", flush=True)
        return
    
    try:
        app_bot = Application.builder().token(TOKEN).build()
        app_bot.add_handler(CommandHandler("start", start))
        app_bot.add_handler(CommandHandler("clear", clear_list))
        app_bot.add_handler(CommandHandler("list", show_list))
        app_bot.add_handler(CallbackQueryHandler(button_callback))
        app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_message))
        
        print("=== БОТ УСПЕШНО ЗАПУЩЕН ===", flush=True)
        # stop_signals=None решает проблему с Gunicorn на Render
        app_bot.run_polling(stop_signals=None)
    except Exception as e:
        print(f"=== ОШИБКА БОТА: {e} ===", flush=True)

# Запуск в фоне при старте Gunicorn
threading.Thread(target=run_bot, daemon=True).start()
