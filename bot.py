import os
import requests

from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

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

    webhook_address = f"{WEBHOOK_URL.rstrip('/')}/webhook"

    result = telegram_request(
        "setWebhook",
        {
            "url": webhook_address,
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


def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation"
    }


def save_profile_to_supabase(profile_data):
    url = f"{SUPABASE_URL}/rest/v1/profiles"

    response = requests.post(
        url,
        headers=supabase_headers(),
        params={
            "on_conflict": "telegram_id"
        },
        json=profile_data,
        timeout=20
    )

    return response


def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.after_request
def apply_cors(response):
    return add_cors_headers(response)


@app.get("/")
def home():
    return "Tanishuv bot backend ishlayapti"


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "tanishuv-bot"
    })


@app.route("/api/profile", methods=["OPTIONS"])
def profile_options():
    return "", 204


@app.post("/api/profile")
def save_profile():
    data = request.get_json(silent=True) or {}

    required_fields = [
        "telegram_id",
        "name",
        "age",
        "gender",
        "bio"
    ]

    missing_fields = [
        field for field in required_fields
        if field not in data
    ]

    if missing_fields:
        return jsonify({
            "ok": False,
            "error": "Quyidagi maydonlar yetishmayapti",
            "fields": missing_fields
        }), 400

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return jsonify({
            "ok": False,
            "error": "Supabase sozlanmagan"
        }), 500

    try:
        telegram_id = int(data["telegram_id"])
        name = str(data["name"]).strip()
        age = int(data["age"])
        gender = str(data["gender"]).strip()
        bio = str(data["bio"]).strip()

        if not name:
            return jsonify({
                "ok": False,
                "error": "Ism bo‘sh bo‘lmasligi kerak"
            }), 400

        if age < 18 or age > 100:
            return jsonify({
                "ok": False,
                "error": "Yosh 18 dan 100 gacha bo‘lishi kerak"
            }), 400

        if gender not in ["Erkak", "Ayol"]:
            return jsonify({
                "ok": False,
                "error": "Jins noto‘g‘ri ko‘rsatilgan"
            }), 400

        if len(bio) < 20:
            return jsonify({
                "ok": False,
                "error": "Bio kamida 20 ta belgidan iborat bo‘lishi kerak"
            }), 400

        profile_data = {
            "telegram_id": telegram_id,
            "name": name,
            "age": age,
            "gender": gender,
            "bio": bio
        }

        response = save_profile_to_supabase(profile_data)

        if response.status_code >= 300:
            print("Supabase xatosi:", response.text)

            return jsonify({
                "ok": False,
                "error": "Profilni Supabase’ga saqlab bo‘lmadi"
            }), 500

        return jsonify({
            "ok": True,
            "message": "Profil Supabase’ga saqlandi",
            "profile": response.json()
        })

    except ValueError:
        return jsonify({
            "ok": False,
            "error": "telegram_id yoki age raqam bo‘lishi kerak"
        }), 400

    except Exception as error:
        print("Server xatosi:", str(error))

        return jsonify({
            "ok": False,
            "error": "Serverda kutilmagan xatolik yuz berdi"
        }), 500


@app.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message")

    if not message:
        return jsonify({"ok": True})

    chat = message.get("chat", {})
    chat_id = chat.get("id")
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
            (
                "Mini App’ni ochish uchun "
                "<b>Tanishuvni boshlash</b> tugmasini bosing."
            )
        )

    return jsonify({"ok": True})


if __name__ == "__main__":
    set_webhook()

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
