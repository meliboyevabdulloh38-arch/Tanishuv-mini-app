import json
import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip().rstrip("/")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
ADMIN_TELEGRAM_ID = os.environ.get("ADMIN_TELEGRAM_ID", "").strip()
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


def is_admin(admin_id):
    return bool(ADMIN_TELEGRAM_ID) and str(admin_id).strip() == ADMIN_TELEGRAM_ID


def admin_denied(admin_id):
    if not is_admin(admin_id):
        return jsonify({"ok": False, "error": "Admin ruxsati yo‘q"}), 403
    return None


@app.get("/api/admin/stats")
def admin_stats():
    denied = admin_denied(request.args.get("admin_id", ""))
    if denied:
        return denied
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers={**supabase_headers(), "Prefer": "count=exact"},
            params={"select": "telegram_id,name,age,gender,bio", "limit": 1000},
            timeout=20,
        )
        if response.status_code >= 300:
            return jsonify({"ok": False, "error": "Statistikani olib bo‘lmadi"}), 500
        users = response.json()
        return jsonify({
            "ok": True,
            "stats": {
                "total_users": len(users),
                "male_users": sum(1 for user in users if user.get("gender") == "Erkak"),
                "female_users": sum(1 for user in users if user.get("gender") == "Ayol"),
                "profiles": users,
            },
        })
    except requests.RequestException as error:
        print("Admin statistika xatosi:", error)
        return jsonify({"ok": False, "error": "Server bilan ulanishda xatolik"}), 500


@app.post("/api/admin/broadcast")
def admin_broadcast():
    data = request.get_json(silent=True) or {}
    denied = admin_denied(data.get("admin_id", ""))
    if denied:
        return denied
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "E’lon matni bo‘sh"}), 400
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=supabase_headers(),
            params={"select": "telegram_id", "limit": 1000},
            timeout=20,
        )
        users = response.json() if response.ok else []
        sent = 0
        failed = 0
        for user in users:
            result = send_message(user.get("telegram_id"), text)
            if result.get("ok"):
                sent += 1
            else:
                failed += 1
        return jsonify({"ok": True, "total": len(users), "sent": sent, "failed": failed})
    except requests.RequestException as error:
        print("Admin e’lon xatosi:", error)
        return jsonify({"ok": False, "error": "E’lon yuborishda xatolik"}), 500


@app.post("/api/admin/block")
def admin_block():
    data = request.get_json(silent=True) or {}
    denied = admin_denied(data.get("admin_id", ""))
    if denied:
        return denied
    user_id = data.get("user_id")
    blocked = bool(data.get("blocked", True))
    if not user_id:
        return jsonify({"ok": False, "error": "Foydalanuvchi ID topilmadi"}), 400
    try:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=supabase_headers(),
            params={"telegram_id": f"eq.{int(user_id)}"},
            json={"is_blocked": blocked},
            timeout=20,
        )
        if response.status_code >= 300:
            print("Bloklash xatosi:", response.text)
            return jsonify({"ok": False, "error": "Foydalanuvchi holati o‘zgarmadi"}), 500
        return jsonify({"ok": True, "blocked": blocked})
    except (ValueError, requests.RequestException) as error:
        print("Admin block xatosi:", error)
        return jsonify({"ok": False, "error": "Bloklashda xatolik"}), 500


@app.get("/api/admin/reports")
def admin_reports():
    denied = admin_denied(request.args.get("admin_id", ""))
    if denied:
        return denied
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/reports",
        headers=supabase_headers(),
        params={"select": "id,reporter_id,reported_id,reason,status,created_at", "status": "eq.open", "order": "created_at.desc", "limit": 200},
        timeout=20,
    )
    if response.status_code >= 300:
        return jsonify({"ok": False, "error": "Shikoyatlarni olib bo‘lmadi"}), 500
    return jsonify({"ok": True, "reports": response.json()})


@app.post("/api/report")
def create_report():
    data = request.get_json(silent=True) or {}
    if not data.get("reporter_id") or not data.get("reported_id") or not data.get("reason"):
        return jsonify({"ok": False, "error": "Shikoyat ma’lumotlari to‘liq emas"}), 400
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/reports",
        headers=supabase_headers(),
        json={"reporter_id": int(data["reporter_id"]), "reported_id": int(data["reported_id"]), "reason": str(data["reason"])[:500]},
        timeout=20,
    )
    if response.status_code >= 300:
        return jsonify({"ok": False, "error": "Shikoyat saqlanmadi"}), 500
    return jsonify({"ok": True})


@app.post("/api/admin/report/resolve")
def resolve_report():
    data = request.get_json(silent=True) or {}
    denied = admin_denied(data.get("admin_id", ""))
    if denied:
        return denied
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/reports",
        headers=supabase_headers(),
        params={"id": f"eq.{int(data.get('report_id', 0))}"},
        json={"status": "resolved"},
        timeout=20,
    )
    return jsonify({"ok": response.status_code < 300})


@app.route("/api/profile", methods=["OPTIONS"])
def profile_options():
    return "", 204


@app.post("/api/profile")
def save_profile():
    data = request.get_json(silent=True) or {}
    required = ["telegram_id", "name", "age", "gender", "bio"]
    missing = [field for field in required if data.get(field) in (None, "")]

    if missing:
        return jsonify({
            "ok": False,
            "error": "Kerakli maydonlar yetishmayapti",
            "fields": missing,
        }), 400

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return jsonify({"ok": False, "error": "Supabase sozlanmagan"}), 500

    try:
        telegram_id = int(str(data["telegram_id"]).strip())
        age = int(float(str(data["age"]).strip()))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Telegram ID yoki yosh noto‘g‘ri"}), 400

    name = str(data.get("name", "")).strip()
    gender = str(data.get("gender", "")).strip()
    bio = str(data.get("bio", "")).strip()
    if age < 18 or age > 100:
        return jsonify({"ok": False, "error": "Yosh 18 dan 100 gacha bo‘lishi kerak"}), 400
    if gender not in ["Erkak", "Ayol"]:
        return jsonify({"ok": False, "error": "Jins noto‘g‘ri tanlangan"}), 400
    if len(bio) < 20:
        return jsonify({"ok": False, "error": "Bio kamida 20 ta belgidan iborat bo‘lishi kerak"}), 400

    # Jadvalda mavjud bo‘lmagan maydonlarni yubormaslik uchun asosiy ustunlar.
    profile_data = {
        "telegram_id": telegram_id,
        "name": name,
        "age": age,
        "gender": gender,
        "bio": bio,
        "last_active": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = save_profile_to_supabase(profile_data)
        if response.status_code >= 300:
            print("Supabase xatosi:", response.text)
            return jsonify({"ok": False, "error": "Profilni saqlab bo‘lmadi"}), 500
        return jsonify({"ok": True, "message": "Profil saqlandi", "profile": response.json()})
    except requests.RequestException as error:
        print("Supabase tarmoq xatosi:", error)
        return jsonify({"ok": False, "error": "Supabase bilan ulanishda xatolik"}), 500


@app.get("/api/profile")
def get_profile():
    telegram_id = request.args.get("telegram_id", "").strip()
    if not telegram_id:
        return jsonify({"ok": False, "error": "Telegram ID topilmadi"}), 400
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return jsonify({"ok": False, "error": "Supabase sozlanmagan"}), 500

    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=supabase_headers(),
            params={
                "select": "telegram_id,name,age,gender,bio",
                "telegram_id": f"eq.{int(telegram_id)}",
                "limit": 1,
            },
            timeout=20,
        )
        if response.status_code >= 300:
            print("Profilni olish xatosi:", response.text)
            return jsonify({"ok": False, "error": "Profilni olib bo‘lmadi"}), 500
        profiles = response.json()
        return jsonify({
            "ok": True,
            "exists": bool(profiles),
            "profile": profiles[0] if profiles else None,
        })
    except (ValueError, requests.RequestException) as error:
        print("Profil GET xatosi:", error)
        return jsonify({"ok": False, "error": "Profilni tekshirishda xatolik"}), 500


@app.get("/api/profiles")
def get_profiles():
    telegram_id = request.args.get("telegram_id", "").strip()
    if not telegram_id:
        return jsonify({"ok": False, "error": "Telegram ID topilmadi"}), 400
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return jsonify({"ok": False, "error": "Supabase sozlanmagan"}), 500

    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=supabase_headers(),
            params={
                "select": "telegram_id,name,age,gender,bio",
                "telegram_id": f"neq.{telegram_id}",
                "limit": 20,
            },
            timeout=20,
        )
        if response.status_code >= 300:
            print("Profillarni olish xatosi:", response.text)
            return jsonify({"ok": False, "error": "Profillarni olib bo‘lmadi"}), 500
        return jsonify({"ok": True, "profiles": response.json()})
    except requests.RequestException as error:
        print("Profillar tarmoq xatosi:", error)
        return jsonify({"ok": False, "error": "Server bilan ulanishda xatolik"}), 500


@app.post("/api/like")
def like_profile():
    data = request.get_json(silent=True) or {}
    from_id = data.get("from_id")
    to_id = data.get("to_id")
    action = data.get("action", "like")
    if not from_id or not to_id or action not in ["like", "dislike"]:
        return jsonify({"ok": False, "error": "Like ma’lumotlari noto‘g‘ri"}), 400
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return jsonify({"ok": False, "error": "Supabase sozlanmagan"}), 500

    try:
        if action == "dislike":
            return jsonify({"ok": True, "match": False})
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/likes",
            headers=supabase_headers(),
            json={"from_id": int(from_id), "to_id": int(to_id)},
            timeout=20,
        )
        if response.status_code >= 300:
            print("Like saqlash xatosi:", response.text)
            return jsonify({"ok": False, "error": "Like saqlanmadi"}), 500
        reverse = requests.get(
            f"{SUPABASE_URL}/rest/v1/likes",
            headers=supabase_headers(),
            params={"select": "id", "from_id": f"eq.{int(to_id)}", "to_id": f"eq.{int(from_id)}", "limit": 1},
            timeout=20,
        )
        match = reverse.ok and bool(reverse.json())
        return jsonify({"ok": True, "match": match})
    except (ValueError, requests.RequestException) as error:
        print("Like tarmoq xatosi:", error)
        return jsonify({"ok": False, "error": "Like xizmatida xatolik"}), 500


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
