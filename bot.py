import json
import os

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip().rstrip("/")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
MINI_APP_URL = os.environ.get(
    "MINI_APP_URL", "https://tanishuv-mini-app.onrender.com"
).strip()

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_request(method, data):
    if not BOT_TOKEN:
        print("BOT_TOKEN mavjud emas")
        return {"ok": False, "description": "BOT_TOKEN missing"}

    try:
        response = requests.post(
            f"{TELEGRAM_API}/{method}",
            json=data,
            timeout=20,
        )
        result = response.json()
        if not result.get("ok"):
            print(f"Telegram {method} xatosi:", result)
        return result
    except requests.RequestException as error:
        print(f"Telegram {method} tarmoq xatosi:", error)
        return {"ok": False, "description": str(error)}


def set_webhook():
    if not BOT_TOKEN or not WEBHOOK_URL:
        print("BOT_TOKEN yoki WEBHOOK_URL mavjud emas")
        return

    webhook_url = f"{WEBHOOK_URL}/webhook"
    result = telegram_request(
        "setWebhook",
        {"url": webhook_url, "drop_pending_updates": True},
    )
    print("Webhook URL:", webhook_url)
    print("Webhook natijasi:", result)


def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard is not None:
        data["reply_markup"] = keyboard
    return telegram_request("sendMessage", data)


def answer_callback_query(callback_query_id, text=None):
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
    return telegram_request("answerCallbackQuery", data)


def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def save_profile_to_supabase(profile_data):
    return requests.post(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=supabase_headers(),
        params={"on_conflict": "telegram_id"},
        json=profile_data,
        timeout=20,
    )


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.get("/")
def home():
    return "Tanishuv bot backend ishlayapti"


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "tanishuv-bot"})


@app.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    print("Telegram update:", json.dumps(update, ensure_ascii=False))

    # Inline keyboard tugmalari uchun callback_query.
    callback_query = update.get("callback_query")
    if callback_query:
        callback_id = callback_query.get("id")
        callback_data = callback_query.get("data", "")
        callback_message = callback_query.get("message", {})
        chat_id = callback_message.get("chat", {}).get("id")

        if callback_id:
            answer_callback_query(callback_id)
        if chat_id:
            if callback_data == "tariffs":
                send_message(chat_id, "Tariflar bo‘limi tez orada qo‘shiladi.")
            elif callback_data == "start_dating":
                send_message(chat_id, "Tanishuvni boshlash uchun Mini App’ni oching.")
            else:
                send_message(chat_id, "Tugma qabul qilindi.")
        return jsonify({"ok": True})

    message = update.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return jsonify({"ok": True})

    # Mini App frontend Telegram.WebApp.sendData(...) yuborganda keladi.
    web_app_data = message.get("web_app_data")
    if web_app_data:
        raw_data = web_app_data.get("data", "")
        try:
            profile_data = json.loads(raw_data)
        except (TypeError, json.JSONDecodeError):
            profile_data = None

        if profile_data and SUPABASE_URL and SUPABASE_SERVICE_KEY:
            profile_data["telegram_id"] = chat_id
            try:
                result = save_profile_to_supabase(profile_data)
                if result.status_code >= 300:
                    print("Supabase xatosi:", result.text)
                    send_message(chat_id, "Profilni saqlashda xatolik yuz berdi.")
                else:
                    send_message(chat_id, "Profilingiz muvaffaqiyatli saqlandi.")
            except requests.RequestException as error:
                print("Supabase tarmoq xatosi:", error)
                send_message(chat_id, "Server bilan ulanishda xatolik yuz berdi.")
        else:
            send_message(chat_id, "Mini App ma’lumotlari qabul qilindi.")
        return jsonify({"ok": True})

    text = (message.get("text") or "").strip()

    if text == "/start":
        keyboard = {
            "keyboard": [
                [
                    {
                        "text": "Tanishuvni boshlash",
                        "web_app": {"url": MINI_APP_URL},
                    }
                ],
                [{"text": "Tariflar"}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
        }
        send_message(
            chat_id,
            "Salom! <b>Tanishuv Olami</b>ga xush kelibsiz.\n\n"
            "Profil yarating va sizga mos insonlar bilan tanishing.",
            keyboard,
        )
    elif text == "Tariflar":
        send_message(chat_id, "Tariflar bo‘limi tez orada qo‘shiladi.")
    else:
        send_message(chat_id, "Mini App’ni ochish uchun tugmani bosing.")

    return jsonify({"ok": True})


# Gunicorn import qilganda webhook o‘rnatiladi.
set_webhook()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
