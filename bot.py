import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_request(method, data):
    response = requests.post(
        f"{TELEGRAM_API}/{method}",
        json=data,
        timeout=20
    )
    return response.json()


def set_webhook():
    if not BOT_TOKEN or not WEBHOOK_URL:
        print("BOT_TOKEN yoki WEBHOOK_URL mavjud emas")
        return

    result = telegram_request(
        "setWebhook",
        {
            "url": f"{WEBHOOK_URL}/webhook",
            "drop_pending_updates": True
        }
    )

    print("Webhook natijasi:", result)


def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if keyboard:
        data["reply_markup"] = keyboard

    return telegram_request("sendMessage", data)


@app.get("/")
def home():
    return "Tanishuv bot backend ishlayapti"


@app.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message")

    if not message:
        return jsonify({"ok": True})

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if not chat_id:
        return jsonify({"ok": True})

    if text == "/start":
        keyboard = {
            "keyboard": [
                [
                    {
                        "text": "Tanishuvni boshlash",
                        "web_app": {
                            "url": "https://tanishuv-mini-app.onrender.com"
                        }
                    }
                ],
                [
                    {
                        "text": "Tariflar"
                    }
                ]
            ],
            "resize_keyboard": True
        }

        send_message(
            chat_id,
            (
                "Salom! <b>Tanishuv Olami</b>ga xush kelibsiz.\n\n"
                "Profil yarating va sizga mos insonlar bilan tanishing."
            ),
            keyboard
        )

    elif text == "Tariflar":
        send_message(
            chat_id,
            "Tariflar bo‘limi keyingi bosqichda qo‘shiladi."
        )

    else:
        send_message(
            chat_id,
            "Mini App’ni ochish uchun "
            "<b>Tanishuvni boshlash</b> tugmasini bosing."
        )

    return jsonify({"ok": True})


set_webhook()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
