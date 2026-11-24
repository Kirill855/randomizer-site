import os
import json
import threading
from flask import Flask, jsonify, render_template
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATA_FILE = "messages.json"
lock = threading.Lock()

app = Flask(__name__)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"messages": [], "index": 0}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
        return jsonify({"message": text, "position": idx + 1, "total": len(msgs), "finished": data["index"] >= len(msgs)})

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пришли текст — он добавится в список.\n/clear — очистить список")

async def add_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    with lock:
        data = load_data()
        data["messages"].append(text)
        save_data(data)
    await update.message.reply_text(f"✅ Добавлено. Всего: {len(data['messages'])}")

async def clear_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with lock:
        save_data({"messages": [], "index": 0})
    await update.message.reply_text("🗑 Список очищен.")

def run_bot():
    if not TOKEN:
        print("ОШИБКА: Токен не задан!", flush=True)
        return
    app_bot = Application.builder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("clear", clear_list))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_message))
    print("Бот запущен!", flush=True)
    app_bot.run_polling(stop_signals=None)

threading.Thread(target=run_bot, daemon=True).start()
