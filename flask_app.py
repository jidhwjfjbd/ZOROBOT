import os
import requests
import time
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

BOT_TOKEN = "8785452517:AAGy-93isP7k1qQxO_LIDb7yZMjieDhJFiw"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_IDS = [8667934765, 8557464787]
PRIMARY_ADMIN_USERNAME = "@sig2siel"
PROOF_CHANNEL_ID = "@Proofsofbotwithdrawal"

# الإعدادات الافتراضية للسحب والإحالة (0.01)
bot_settings = {
    "referral_reward": 0.01,
    "min_withdrawal": 0.01
}

app = Flask(__name__)

BOT_USERNAME = "ZoroBot"
try:
    bot_info = requests.get(f"{TELEGRAM_API_URL}/getMe").json()
    if bot_info.get("ok"):
        BOT_USERNAME = bot_info["result"]["username"]
except Exception:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        chat_id BIGINT PRIMARY KEY,
                        username TEXT,
                        balance REAL DEFAULT 0.0,
                        wallet TEXT,
                        verified INTEGER DEFAULT 0,
                        banned INTEGER DEFAULT 0,
                        invited_by BIGINT,
                        last_active DOUBLE PRECISION
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS fingerprints (
                        fingerprint TEXT PRIMARY KEY,
                        chat_id BIGINT
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS referrals (
                        referrer_id BIGINT,
                        referred_id BIGINT,
                        PRIMARY KEY (referrer_id, referred_id)
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS pending_withdrawals (
                        w_id TEXT PRIMARY KEY,
                        user_id BIGINT,
                        amount REAL,
                        wallet TEXT,
                        username TEXT,
                        tx_hash TEXT
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()

def get_db():
    return psycopg2.connect(DATABASE_URL)

forced_channels = []  
forced_bots = []      
user_task_progress = {} 
admin_states = {}
user_states = {}      
temp_bot_data = {}    
broadcast_data = {}
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZORO Security - نظام التحقق</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fingerprintjs2/2.1.4/fingerprint2.min.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
        .card { background: #1e293b; padding: 30px 24px; border-radius: 20px; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5); width: 100%; max-width: 380px; border: 1px solid #334155; }
        .btn { background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); color: white; border: none; padding: 14px; border-radius: 12px; font-size: 16px; font-weight: bold; width: 100%; cursor: pointer; margin-bottom: 12px; }
        .warning-box { background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #fca5a5; padding: 10px; border-radius: 8px; font-size: 13px; margin-top: 10px; display: none; }
    </style>
</head>
<body>
    <div class="card">
        <h2>نظام حماية ZORO</h2>
        <p style="color: #94a3b8; font-size: 14px; margin-bottom: 20px;">قم بتأكيد بصمة جهازك لتنشيط الحساب نهائياً.</p>
        <button id="verifyBtn" class="btn" onclick="processVerification()">تأكيد الهوية والجهاز ✨</button>
        <div id="channels-warning" class="warning-box">⚠️ يجب إكمال القنوات والبوتات أولاً!</div>
        <div id="status" style="margin-top:15px; font-size:14px; font-weight:600;"></div>
    </div>
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        
        fetch('/check_status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : 0 })
        }).then(res => res.json()).then(data => {
            if (data.has_pending_tasks) {
                document.getElementById('channels-warning').style.display = 'block';
            } else {
                document.getElementById('channels-warning').style.display = 'none';
            }
        }).catch(() => {});

        function processVerification() {
            Fingerprint2.get((components) => {
                const values = components.map((pair) => pair.value);
                const hash = Fingerprint2.x64hash128(values.join(''), 31);
                const user = tg.initDataUnsafe.user || { id: 0 };
                fetch('/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: user.id, fingerprint: hash })
                }).then(res => res.json()).then(data => {
                    if (data.success) { 
                        document.getElementById('status').style.color = '#34d399';
                        document.getElementById('status').innerText = "✅ تم التحقق بنجاح!"; 
                        setTimeout(() => tg.close(), 1200); 
                    } else { 
                        document.getElementById('status').style.color = '#f87171';
                        document.getElementById('status').innerText = data.message || "❌ خطأ!"; 
                    }
                });
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/check_status', methods=['POST'])
def check_status():
    data = request.json or {}
    user_id = data.get('user_id', 0)
    try:
        user_id = int(user_id)
    except ValueError:
        pass
    
    t_type, _ = get_next_pending_task(user_id)
    has_pending = True if (forced_channels or forced_bots) and t_type in ["channel", "bots_all"] else False
    return jsonify({'has_pending_tasks': has_pending})

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json or {}
    user_id, fingerprint = data.get('user_id'), data.get('fingerprint')
    if not user_id or not fingerprint: 
        return jsonify({'success': False}), 400
    try: 
        user_id = int(user_id)
    except ValueError: 
        pass
    
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT banned FROM users WHERE chat_id = %s", (user_id,))
    row = cursor.fetchone()
    if row and row["banned"] == 1:
        cursor.close()
        db.close()
        return jsonify({'success': False, 'message': '🚫 محظور!'}), 403

    cursor.execute("INSERT INTO users (chat_id, balance, verified, banned, last_active) VALUES (%s, 0.0, 0, 0, %s) ON CONFLICT (chat_id) DO UPDATE SET last_active = EXCLUDED.last_active", (user_id, time.time()))
    db.commit()

    if user_id in ADMIN_IDS:
        cursor.execute("UPDATE users SET verified = 1 WHERE chat_id = %s", (user_id,))
        db.commit()
        cursor.close()
        db.close()
        return jsonify({'success': True})

    cursor.execute("SELECT chat_id FROM fingerprints WHERE fingerprint = %s", (fingerprint,))
    f_row = cursor.fetchone()
    if f_row and f_row["chat_id"] != user_id:
        cursor.execute("UPDATE users SET banned = 1 WHERE chat_id = %s", (user_id,))
        db.commit()
        cursor.close()
        db.close()
        return jsonify({'success': False, 'message': '🚫 تم حظرك نهائياً لمخالفة سياسة الحساب الواحد!'}), 403
    
    cursor.execute("INSERT INTO fingerprints (fingerprint, chat_id) VALUES (%s, %s) ON CONFLICT (fingerprint) DO UPDATE SET chat_id = EXCLUDED.chat_id", (fingerprint, user_id))
    db.commit()
    
    if forced_channels or forced_bots:
        task_type, _ = get_next_pending_task(user_id)
        if task_type != "done" and task_type != "webapp":
            cursor.close()
            db.close()
            return jsonify({'success': False, 'message': '⚠️ يجب إكمال القنوات والبوتات أولاً!'}), 400

    cursor.execute("SELECT verified FROM users WHERE chat_id = %s", (user_id,))
    v_row = cursor.fetchone()
    is_already_verified = v_row["verified"] if v_row else 0

    cursor.execute("UPDATE users SET verified = 1 WHERE chat_id = %s", (user_id,))
    db.commit()
    
    if not is_already_verified:
        cursor.execute("SELECT invited_by FROM users WHERE chat_id = %s", (user_id,))
        u_row = cursor.fetchone()
        if u_row and u_row["invited_by"]:
            referrer_id = u_row["invited_by"]
            if referrer_id != user_id:
                cursor.execute("SELECT 1 FROM referrals WHERE referrer_id = %s AND referred_id = %s", (referrer_id, user_id))
                if not cursor.fetchone():
                    reward = bot_settings["referral_reward"]
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id = %s", (reward, referrer_id))
                    cursor.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (referrer_id, user_id))
                    db.commit()
                    send_telegram_message(referrer_id, f"🎉 شخص ما انضم عبر رابط إحالتك وأتم التحقق بنجاح! حصلت على `{reward} TON`.")

    cursor.close()
    db.close()
    return jsonify({'success': True})
def get_next_pending_task(chat_id):
    if chat_id in ADMIN_IDS:
        return "done", None

    progress = user_task_progress.setdefault(chat_id, {"channels_done": False, "bots_done": False, "bot_repeat_count": 0})

    if forced_channels and not progress["channels_done"]:
        missing_channels = []
        for ch in forced_channels:
            clean_ch = ch.strip()
            try:
                res = requests.get(f"{TELEGRAM_API_URL}/getChatMember", params={"chat_id": clean_ch, "user_id": chat_id}).json()
                if not res.get("ok") or res["result"]["status"] not in ["creator", "administrator", "member"]:
                    missing_channels.append(clean_ch)
            except Exception:
                missing_channels.append(clean_ch)
        
        if not missing_channels:
            progress["channels_done"] = True
        else:
            return "channel", missing_channels
    else:
        progress["channels_done"] = True

    if forced_bots and not progress["bots_done"]:
        target_repeats = 4  
        current_repeats = progress.get("bot_repeat_count", 0)
        if current_repeats < target_repeats:
            return "bots_all", forced_bots
        else:
            progress["bots_done"] = True

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT verified FROM users WHERE chat_id = %s", (chat_id,))
    row = cursor.fetchone()
    cursor.close()
    db.close()
    
    is_verified = row["verified"] if row else 0
    if not is_verified:
        return "webapp", None

    return "done", None

def send_next_task_prompt(chat_id):
    task_type, data = get_next_pending_task(chat_id)

    if task_type == "channel":
        buttons = []
        for ch in data:
            ch_name = ch.replace('@', '')
            buttons.append([{"text": f"📢 انضمام إلى {ch}", "url": f"https://t.me/{ch_name}"}])
        buttons.append([{"text": "✅ تحقق من الاشتراك", "callback_data": "check_next_task"}])
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "⚠️ **الخطوة الأولى:** يجب عليك الانضمام إلى القنوات التالية أولاً للاستمرار:", "reply_markup": {"inline_keyboard": buttons}, "parse_mode": "Markdown"})

    elif task_type == "bots_all":
        buttons = []
        for b_info in data:
            b_url = b_info["url"]
            if not b_url.startswith("http"):
                b_url = f"https://t.me/{b_info['url'].replace('@', '')}"
            buttons.append([{"text": f"🤖 تسجيل في بوت: {b_info['name']}", "url": b_url}])
        buttons.append([{"text": "✅ تحقق من التسجيل", "callback_data": "click_all_bots"}])
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "🤖 **مهام البوتات الإجبارية:**\n\nيجب التسجيل في جميع البوتات أعلاه أولاً ثم الضغط على زر التحقق أدناه للمتابعة.", "reply_markup": {"inline_keyboard": buttons}, "parse_mode": "Markdown"})

    elif task_type == "webapp":
        render_domain = os.environ.get("RENDER_EXTERNAL_URL", "https://zorobot-qbm3.onrender.com")
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "🛡 **الخطوة الأخيرة:** قم بتوثيق جهازك عبر زر الأمان أدناه لتنشيط الحساب:", "reply_markup": {"inline_keyboard": [[{"text": "🛡 توثيق الجهاز الآن (ZORO)", "web_app": {"url": render_domain}}]]}, "parse_mode": "Markdown"})

    elif task_type == "done":
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT verified FROM users WHERE chat_id = %s", (chat_id,))
        row = cursor.fetchone()
        is_verified = row["verified"] if row else 0

        if not is_verified and chat_id not in ADMIN_IDS:
            cursor.execute("UPDATE users SET verified = 1 WHERE chat_id = %s", (chat_id,))
            cursor.execute("SELECT invited_by FROM users WHERE chat_id = %s", (chat_id,))
            u_row = cursor.fetchone()
            db.commit()
            
            if u_row and u_row["invited_by"]:
                referrer_id = u_row["invited_by"]
                if referrer_id != chat_id:
                    cursor.execute("SELECT 1 FROM referrals WHERE referrer_id = %s AND referred_id = %s", (referrer_id, chat_id))
                    if not cursor.fetchone():
                        reward = bot_settings["referral_reward"]
                        cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id = %s", (reward, referrer_id))
                        cursor.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (referrer_id, chat_id))
                        db.commit()
                        
                        cursor.execute("SELECT username FROM users WHERE chat_id = %s", (chat_id,))
                        ref_user_row = cursor.fetchone()
                        new_user_username = ref_user_row["username"] if ref_user_row and ref_user_row["username"] else "مستخدم جديد"
                        send_telegram_message(referrer_id, f"🎉 سجل @{new_user_username} الدخول للبوت عبر رابطك واجتاز شروط التحقق والمهام بنجاح! حصلت على `{reward} TON`.")
        cursor.close()
        db.close()
        send_main_menu(chat_id, "✨ تمت كافة خطوات التحقق بنجاح وأصبح حسابك مفعلاً بالكامل!")

def execute_broadcast(admin_id):
    b_msg = broadcast_data.get(admin_id)
    if not b_msg: 
        return
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT chat_id FROM users")
    users = cursor.fetchall()
    cursor.close()
    db.close()

    success = 0
    for u in users:
        uid = u["chat_id"]
        try:
            requests.post(f"{TELEGRAM_API_URL}/copyMessage", json={
                "chat_id": uid,
                "from_chat_id": admin_id,
                "message_id": b_msg
            })
            success += 1
        except Exception: 
            pass
    broadcast_data.pop(admin_id, None)
    send_telegram_message(admin_id, f"📊 تمت الإذاعة بنجاح إلى `{success}` مستخدم.")

def send_main_menu(chat_id, text):
    reply_keyboard = {
        "keyboard": [
            [{"text": "🎁 رابط الإحالة"}, {"text": "💎 رصيدي والسحب"}],
            [{"text": "💳 ربط المحفظة"}, {"text": "📊 إحصائيات البوت"}],
            [{"text": "📞 الدعم الفني"}]
        ],
        "resize_keyboard": True
    }
    if chat_id in ADMIN_IDS:
        admin_inline = {
            "inline_keyboard": [
                [{"text": "📦 طلبات السحب المعلقة", "callback_data": "check_pending_withdrawals"}],
                [{"text": "📢 إذاعة جماعية", "callback_data": "start_broadcast"}],
                [{"text": "💰 تعديل الإحالة", "callback_data": "set_ref_reward"}, {"text": "💸 تعديل السحب", "callback_data": "set_min_withdrawal"}],
                [{"text": "📢 إضافة قناة", "callback_data": "add_channel"}, {"text": "🗑 حذف قناة", "callback_data": "del_channel"}],
                [{"text": "🤖 إضافة بوت", "callback_data": "add_bot"}, {"text": "🗑️ حذف بوت", "callback_data": "del_bot"}]
            ]
        }
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "📂 **لوحة التحكم الإدارية:**", "parse_mode": "Markdown", "reply_markup": admin_inline})
    send_telegram_message(chat_id, text, reply_markup=reply_keyboard)

def send_telegram_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup: 
        payload["reply_markup"] = reply_markup
    try: 
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)
    except Exception: 
        pass
@app.route('/webhook', methods=['POST'])
def webhook():
    global forced_bots, forced_channels
    update = request.get_json()
    if not update: 
        return "OK", 200

    if "message" in update:
        chat_type = update["message"]["chat"].get("type", "private")
        if chat_type in ["group", "supergroup"]:
            return "OK", 200

    if "callback_query" in update:
        chat_type = update["callback_query"]["message"]["chat"].get("type", "private")
        if chat_type in ["group", "supergroup"]:
            try:
                requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": update["callback_query"]["id"]})
            except Exception:
                pass
            return "OK", 200

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id, chat_id, msg_id, data = cb["id"], cb["message"]["chat"]["id"], cb["message"]["message_id"], cb.get("data", "")
        try: 
            requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id})
        except Exception: 
            pass

        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        if chat_id in ADMIN_IDS:
            if data == "check_pending_withdrawals":
                cursor.execute("SELECT * FROM pending_withdrawals")
                pend_rows = cursor.fetchall()
                if not pend_rows:
                    send_telegram_message(chat_id, "✅ لا توجد أي طلبات سحب معلقة حالياً.")
                else:
                    send_telegram_message(chat_id, f"📦 لديك `{len(pend_rows)}` طلب سحب معلق:")
                    for req in pend_rows:
                        w_id, u_id, amount, wallet, username = req["w_id"], req["user_id"], req["amount"], req["wallet"], req["username"]
                        kb = {"inline_keyboard": [[{"text": "✅ قبول", "callback_data": f"approve_w_{w_id}"}, {"text": "❌ رفض", "callback_data": f"reject_w_{w_id}"}]]}
                        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                            "chat_id": chat_id, 
                            "text": f"📌 **طلب معلق:**\n👤 User: @{username}\n🆔 Chat ID: `{u_id}`\n💎 Amount: `{amount} TON`\n💳 Wallet: `{wallet}`", 
                            "reply_markup": kb, 
                            "parse_mode": "Markdown"
                        })
                cursor.close()
                db.close()
                return "OK", 200

            if data.startswith("approve_w_") or data.startswith("reject_w_"):
                parts = data.split("_")
                action, w_id = parts[0], parts[2]
                cursor.execute("SELECT * FROM pending_withdrawals WHERE w_id = %s", (w_id,))
                w_row = cursor.fetchone()
                if w_row:
                    u_id, amount, wallet, username, tx_hash = w_row["user_id"], w_row["amount"], w_row["wallet"], w_row["username"], w_row["tx_hash"]
                    cursor.execute("DELETE FROM pending_withdrawals WHERE w_id = %s", (w_id,))
                    db.commit()

                    if action == "approve":
                        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        proof_text = f"💎 **Gram Payment Successful!**\n\n👤 المستخدم: @{username}\n💵 الكمية: `{amount}` TON\n📥 المحفظة: `{wallet}`\n⏰ التوقيت: `{current_time_str}`\n🔗 TX: `{tx_hash}`\n■ Status: ✅ Successful"
                        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": PROOF_CHANNEL_ID, "text": proof_text, "parse_mode": "Markdown"})
                        
                        user_success_msg = f"🎉 **تم قبول طلب السحب الخاص بك بنجاح!**\n\n👤 اليوزر: @{username}\n💵 الكمية: `{amount} TON`\n⏰ التوقيت: `{current_time_str}`"
                        send_telegram_message(u_id, user_success_msg)
                        
                        requests.post(f"{TELEGRAM_API_URL}/editMessageText", json={"chat_id": chat_id, "message_id": msg_id, "text": f"✅ **تم قبول السحب ونشره في القناة:**\n\n{proof_text}", "parse_mode": "Markdown"})
                    elif action == "reject":
                        if u_id not in ADMIN_IDS: 
                            cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id = %s", (amount, u_id))
                            db.commit()
                        send_telegram_message(u_id, f"❌ **عذراً، تم رفض طلب سحبك (`{amount} TON`) وتم إرجاع الرصيد لحسابك.**")
                        requests.post(f"{TELEGRAM_API_URL}/editMessageText", json={"chat_id": chat_id, "message_id": msg_id, "text": "❌ **تم رفض الطلب واسترجاع الرصيد.**", "parse_mode": "Markdown"})
                cursor.close()
                db.close()
                return "OK", 200

            if data == "start_broadcast":
                admin_states[chat_id] = "waiting_broadcast"
                send_telegram_message(chat_id, "📢 **أرسل الآن الرسالة التي تريد إذاعتها (صورة، فيديو، نص، ملف، أو أزرار وروابط):**")
            elif data == "set_ref_reward": 
                admin_states[chat_id] = "waiting_ref_reward"
                send_telegram_message(chat_id, "✍️ أدخل سعر الإحالة الجديد:")
            elif data == "set_min_withdrawal": 
                admin_states[chat_id] = "waiting_min_withdrawal"
                send_telegram_message(chat_id, "✍️ أدخل الحد الأدنى للسحب الجديد:")
            elif data == "add_channel": 
                admin_states[chat_id] = "waiting_add_channel"
                send_telegram_message(chat_id, "📢 أرسل معرف القناة (مثال: `@ChannelUsername`):")
            elif data == "del_channel":
                if not forced_channels: 
                    send_telegram_message(chat_id, "⚠ لا توجد قنوات مسجلة.")
                else:
                    buttons = [[{"text": f"🗑️ حذف {ch}", "callback_data": f"remove_ch_{ch}"}] for ch in forced_channels]
                    send_telegram_message(chat_id, "🗑 اختر القناة المراد حذفها:", reply_markup={"inline_keyboard": buttons})
            elif data.startswith("remove_ch_"):
                ch_to_remove = data.replace("remove_ch_", "")
                if ch_to_remove in forced_channels: 
                    forced_channels.remove(ch_to_remove)
                send_telegram_message(chat_id, f"✅ تم حذف القناة `{ch_to_remove}`.")
            elif data == "add_bot":
                admin_states[chat_id] = "waiting_bot_url"
                send_telegram_message(chat_id, "🤖 أرسل رابط البوت أو رابط الميني أب (Mini App):")
            elif data == "del_bot":
                if not forced_bots: 
                    send_telegram_message(chat_id, "⚠ لا توجد بوتات مسجلة.")
                else:
                    buttons = [[{"text": f"🗑️ حذف {b['name']}", "callback_data": f"remove_bot_{b['name']}"}] for b in forced_bots]
                    send_telegram_message(chat_id, "🗑 اختر البوت المراد حذفه:", reply_markup={"inline_keyboard": buttons})
            elif data.startswith("remove_bot_"):
                b_name_del = data.replace("remove_bot_", "")
                forced_bots[:] = [b for b in forced_bots if b['name'] != b_name_del]
                send_telegram_message(chat_id, f"✅ تم حذف البوت بنجاح.")
            elif data == "confirm_broadcast":
                execute_broadcast(chat_id)
            cursor.close()
            db.close()
            return "OK", 200

        if chat_id not in ADMIN_IDS and data == "check_next_task":
            cursor.close()
            db.close()
            send_next_task_prompt(chat_id)
            return "OK", 200

        if chat_id not in ADMIN_IDS and data == "click_all_bots":
            progress = user_task_progress.setdefault(chat_id, {"channels_done": False, "bots_done": False, "bot_repeat_count": 0})
            progress["bot_repeat_count"] = progress.get("bot_repeat_count", 0) + 1
            
            target_repeats = 4 
            if progress["bot_repeat_count"] >= target_repeats:
                progress["bots_done"] = True
            
            cursor.close()
            db.close()
            send_next_task_prompt(chat_id)
            return "OK", 200

        cursor.close()
        db.close()
        return "OK", 200
    if "message" in update:
        msg = update["message"]
        chat_id, text = msg["chat"]["id"], msg.get("text", "")
        username = msg["from"].get("username") or f"user_{chat_id}"
        
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        cursor.execute("INSERT INTO users (chat_id, username, balance, verified, banned, last_active) VALUES (%s, %s, 0.0, 0, 0, %s) ON CONFLICT (chat_id) DO UPDATE SET username = EXCLUDED.username, last_active = EXCLUDED.last_active", (chat_id, username, time.time()))
        db.commit()

        user_task_progress.setdefault(chat_id, {"channels_done": False, "bots_done": False, "bot_repeat_count": 0})["username"] = username

        if text == "🔙 العودة للقائمة الرئيسية":
            user_states.pop(chat_id, None)
            admin_states.pop(chat_id, None)
            cursor.close()
            db.close()
            task_type, _ = get_next_pending_task(chat_id)
            if task_type != "done":
                send_next_task_prompt(chat_id)
            else:
                send_main_menu(chat_id, "🔙 تم العودة للقائمة الرئيسية:")
            return "OK", 200

        if chat_id in ADMIN_IDS:
            if text.startswith("📦 طلبات السحب المعلقة"):
                cursor.execute("SELECT * FROM pending_withdrawals")
                pend_rows = cursor.fetchall()
                if not pend_rows:
                    send_telegram_message(chat_id, "✅ لا توجد أي طلبات سحب معلقة حالياً.")
                else:
                    send_telegram_message(chat_id, f"📦 لديك `{len(pend_rows)}` طلب سحب معلق:")
                    for req in pend_rows:
                        w_id, u_id, amount, wallet, username = req["w_id"], req["user_id"], req["amount"], req["wallet"], req["username"]
                        kb = {"inline_keyboard": [[{"text": "✅ قبول", "callback_data": f"approve_w_{w_id}"}, {"text": "❌ رفض", "callback_data": f"reject_w_{w_id}"}]]}
                        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                            "chat_id": chat_id, 
                            "text": f"📌 **طلب معلق:**\n👤 User: @{username}\n🆔 Chat ID: `{u_id}`\n💎 Amount: `{amount} TON`\n💳 Wallet: `{wallet}`", 
                            "reply_markup": kb, 
                            "parse_mode": "Markdown"
                        })
                cursor.close()
                db.close()
                return "OK", 200

            if chat_id in admin_states:
                state = admin_states[chat_id]
                if state == "waiting_broadcast":
                    admin_states.pop(chat_id, None)
                    broadcast_data[chat_id] = msg["message_id"]
                    send_telegram_message(chat_id, "هل تريد تأكيد إرسال هذه الرسالة كإذاعة لجميع المستخدمين؟", reply_markup={"inline_keyboard": [[{"text": "🚀 إرسال الآن", "callback_data": "confirm_broadcast"}]]})
                elif state == "waiting_ref_reward":
                    admin_states.pop(chat_id, None)
                    bot_settings["referral_reward"] = float(text.strip())
                    send_telegram_message(chat_id, "✅ تم تحديث سعر الإحالة بنجاح.")
                elif state == "waiting_min_withdrawal":
                    admin_states.pop(chat_id, None)
                    bot_settings["min_withdrawal"] = float(text.strip())
                    send_telegram_message(chat_id, "✅ تم تحديث الحد الأدنى للسحب بنجاح.")
                elif state == "waiting_add_channel":
                    admin_states.pop(chat_id, None)
                    ch = text.strip()
                    if ch not in forced_channels: 
                        forced_channels.append(ch)
                    user_task_progress.clear()
                    send_telegram_message(chat_id, f"✅ تم إضافة القناة `{ch}` بنجاح وتحديث المهام لجميع المستخدمين.")
                elif state == "waiting_bot_url":
                    temp_bot_data[chat_id] = {"url": text.strip()}
                    admin_states[chat_id] = "waiting_bot_name"
                    send_telegram_message(chat_id, "✍️ أرسل الاسم الذي سيظهر للمستخدم كمميز في قائمة البوتات الإجبارية:")
                elif state == "waiting_bot_name":
                    admin_states.pop(chat_id, None)
                    b_url = temp_bot_data.pop(chat_id, {}).get("url", "")
                    b_name = text.strip()
                    forced_bots.append({"name": b_name, "url": b_url})
                    user_task_progress.clear()
                    send_telegram_message(chat_id, f"✅ تم إضافة البوت `{b_name}` بنجاح ليظهر لجميع المستخدمين.")
                cursor.close()
                db.close()
                return "OK", 200

        if chat_id in user_states:
            state = user_states.pop(chat_id, None)
            if state == "waiting_wallet":
                wallet = text.strip()
                cursor.execute("UPDATE users SET wallet = %s WHERE chat_id = %s", (wallet, chat_id))
                db.commit()
                cursor.close()
                db.close()
                send_telegram_message(chat_id, "✅ **تم حفظ عنوان محفظتك بنجاح!**")
                send_main_menu(chat_id, "يمكنك الآن طلب السحب من خيار 'رصيدي والسحب'.")
                return "OK", 200
            elif state == "waiting_withdraw_amount":
                try:
                    amount = float(text.strip())
                except ValueError:
                    cursor.close()
                    db.close()
                    send_telegram_message(chat_id, "❌ يرجى إدخال رقم صحيح كمية السحب:")
                    user_states[chat_id] = "waiting_withdraw_amount"
                    return "OK", 200

                cursor.execute("SELECT balance, wallet FROM users WHERE chat_id = %s", (chat_id,))
                urow = cursor.fetchone()
                if not urow:
                    cursor.close()
                    db.close()
                    return "OK", 200
                
                balance, wallet = urow["balance"], urow["wallet"]
                min_w = bot_settings["min_withdrawal"]

                if not wallet:
                    cursor.close()
                    db.close()
                    user_states.pop(chat_id, None)
                    send_telegram_message(chat_id, "⚠️ يجب عليك ربط محفظتك أولاً قبل طلب السحب عبر الضغط على زر '💳 ربط المحفظة'.")
                    return "OK", 200

                if amount < min_w:
                    cursor.close()
                    db.close()
                    user_states[chat_id] = "waiting_withdraw_amount"
                    send_telegram_message(chat_id, f"❌ عذراً، الحد الأدنى للسحب هو `{min_w} TON`.")
                    return "OK", 200

                if amount > balance:
                    cursor.close()
                    db.close()
                    user_states[chat_id] = "waiting_withdraw_amount"
                    send_telegram_message(chat_id, "❌ رصيدك غير كافٍ لهذا السحب.")
                    return "OK", 200

                cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id = %s", (amount, chat_id))
                db.commit()

                w_id = hashlib.md5(f"{chat_id}_{time.time()}".encode()).hexdigest()[:10]
                tx_hash = hashlib.sha256(f"{w_id}_{wallet}_{amount}".encode()).hexdigest()[:24]

                cursor.execute("INSERT INTO pending_withdrawals (w_id, user_id, amount, wallet, username, tx_hash) VALUES (%s, %s, %s, %s, %s, %s)", 
                               (w_id, chat_id, amount, wallet, username, tx_hash))
                db.commit()

                for admin_id in ADMIN_IDS:
                    kb = {"inline_keyboard": [[{"text": "✅ قبول", "callback_data": f"approve_w_{w_id}"}, {"text": "❌ رفض", "callback_data": f"reject_w_{w_id}"}]]}
                    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                        "chat_id": admin_id,
                        "text": f"🚨 **طلب سحب جديد معلق:**\n\n👤 المستخدم: @{username}\n🆔 ID: `{chat_id}`\n💎 الكمية: `{amount} TON`\n💳 المحفظة: `{wallet}`",
                        "reply_markup": kb,
                        "parse_mode": "Markdown"
                    })

                cursor.close()
                db.close()
                user_states.pop(chat_id, None)
                send_telegram_message(chat_id, f"✅ **تم إرسال طلب السحب بنجاح!**\n\nتم اقتطاع `{amount} TON` من رصيدك وهو قيد المراجعة من قبل الإدارة.")
                send_main_menu(chat_id, "القائمة الرئيسية:")
                return "OK", 200

        if text == "/start" or text.startswith("/start "):
            parts = text.split(" ")
            if len(parts) > 1:
                ref_arg = parts[1]
                if ref_arg.isdigit():
                    referrer_id = int(ref_arg)
                    if referrer_id != chat_id and chat_id not in ADMIN_IDS:
                        cursor.execute("SELECT invited_by FROM users WHERE chat_id = %s", (chat_id,))
                        r_chk = cursor.fetchone()
                        if r_chk and not r_chk["invited_by"]:
                            cursor.execute("UPDATE users SET invited_by = %s WHERE chat_id = %s", (referrer_id, chat_id))
                            db.commit()

            cursor.execute("SELECT verified FROM users WHERE chat_id = %s", (chat_id,))
            row = cursor.fetchone()
            is_verified = row["verified"] if row else 0

            if chat_id in ADMIN_IDS:
                cursor.execute("SELECT COUNT(*) as cnt FROM pending_withdrawals")
                p_row = cursor.fetchone()
                pend_count = p_row["cnt"] if p_row else 0
                
                admin_kb = {
                    "inline_keyboard": [
                        [{"text": f"📦 طلبات السحب المعلقة ({pend_count})", "callback_data": "check_pending_withdrawals"}],
                        [{"text": "📢 إذاعة جماعية", "callback_data": "start_broadcast"}],
                        [{"text": "💰 تعديل الإحالة", "callback_data": "set_ref_reward"}, {"text": "💸 تعديل السحب", "callback_data": "set_min_withdrawal"}],
                        [{"text": "📢 إضافة قناة", "callback_data": "add_channel"}, {"text": "🗑 حذف قناة", "callback_data": "del_channel"}],
                        [{"text": "🤖 إضافة بوت", "callback_data": "add_bot"}, {"text": "🗑️ حذف بوت", "callback_data": "del_bot"}]
                    ]
                }
                requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"👋 أهلاً بك يا مشرف البوت (`{BOT_USERNAME}`).\nلديك صلاحيات كاملة لإدارة البوت والطلبات المعلقة.",
                    "reply_markup": admin_kb,
                    "parse_mode": "Markdown"
                })
                cursor.close()
                db.close()
                send_main_menu(chat_id, "لوحة التحكم جاهزة:")
                return "OK", 200

            cursor.close()
            db.close()
            task_type, _ = get_next_pending_task(chat_id)
            if task_type != "done":
                send_next_task_prompt(chat_id)
            else:
                send_main_menu(chat_id, "✨ أهلاً بك مجدداً في بوت ZORO!")
            return "OK", 200

        elif text == "🎁 رابط الإحالة":
            ref_link = f"https://t.me/{BOT_USERNAME}?start={chat_id}"
            cursor.execute("SELECT COUNT(*) as count FROM referrals WHERE referrer_id = %s", (chat_id,))
            ref_count = cursor.fetchone()["count"]
            cursor.close()
            db.close()
            msg_text = f"🎁 **نظام الإحالات والأرباح:**\n\n🔗 رابط إحالتك الخاص:\n`{ref_link}`\n\n👥 عدد الأشخاص الذين دعيتهم: `{ref_count}` مستخدم\n💰 مكافأة الإحالة لكل شخص: `{bot_settings['referral_reward']} TON`\n\nشارك الرابط مع أصدقائك واجمع الأرباح!"
            send_telegram_message(chat_id, msg_text)
            return "OK", 200

        elif text == "💎 رصيدي والسحب":
            cursor.execute("SELECT balance, wallet FROM users WHERE chat_id = %s", (chat_id,))
            urow = cursor.fetchone()
            cursor.close()
            db.close()
            
            if not urow or not urow["wallet"]:
                send_telegram_message(chat_id, "⚠️ يجب عليك ربط محفظتك أولاً عبر زر '💳 ربط المحفظة' قبل طلب السحب.")
                return "OK", 200
            
            if urow["balance"] < bot_settings["min_withdrawal"]:
                send_telegram_message(chat_id, f"❌ عذراً، رصيدك الحالي (`{urow['balance']} TON`) أقل من الحد الأدنى للسحب (`{bot_settings['min_withdrawal']} TON`).")
                return "OK", 200

            user_states[chat_id] = "waiting_withdraw_amount"
            send_telegram_message(chat_id, f"💸 **طلب سحب الأرباح:**\n\nرصيدك المتاح: `{urow['balance']} TON`\nالحد الأدنى: `{bot_settings['min_withdrawal']} TON`\n\n✍️ أرسل الآن الكمية التي تريد سحبها:", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
            return "OK", 200

        elif text == "💳 ربط المحفظة":
            user_states[chat_id] = "waiting_wallet"
            cursor.close()
            db.close()
            send_telegram_message(chat_id, "💳 **ربط محفظة TON:**\n\nأرسل الآن عنوان محفظتك (مثل: `UQD...` أو `EQD...`):", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
            return "OK", 200

        elif text == "📊 إحصائيات البوت":
            cursor.execute("SELECT COUNT(*) as total FROM users")
            tot_users = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) as verified FROM users WHERE verified = 1")
            ver_users = cursor.fetchone()["verified"]
            cursor.close()
            db.close()
            send_telegram_message(chat_id, f"📊 **إحصائيات بوت {BOT_USERNAME}:**\n\n👥 إجمالي المستخدمين: `{tot_users}`\n✅ المستخدمون الموثقون: `{ver_users}`")
            return "OK", 200

        elif text == "📞 الدعم الفني":
            cursor.close()
            db.close()
            send_telegram_message(chat_id, f"📞 للإبلاغ عن مشكلة أو الاستفسار، يمكنك التواصل مع الإدارة عبر المعرف التالي:\n\n{PRIMARY_ADMIN_USERNAME}")
            return "OK", 200

        cursor.close()
        db.close()

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id, chat_id, data = cb["id"], cb["message"]["chat"]["id"], cb.get("data", "")
        if data == "request_withdrawal":
            db = get_db()
            cursor = db.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT balance, wallet FROM users WHERE chat_id = %s", (chat_id,))
            urow = cursor.fetchone()
            cursor.close()
            db.close()
            
            if not urow or not urow["wallet"]:
                send_telegram_message(chat_id, "⚠️ يجب عليك ربط محفظتك أولاً عبر زر '💳 ربط المحفظة' قبل طلب السحب.")
                return "OK", 200
            
            if urow["balance"] < bot_settings["min_withdrawal"]:
                send_telegram_message(chat_id, f"❌ عذراً، رصيدك الحالي (`{urow['balance']} TON`) أقل من الحد الأدنى للسحب (`{bot_settings['min_withdrawal']} TON`).")
                return "OK", 200

            user_states[chat_id] = "waiting_withdraw_amount"
            send_telegram_message(chat_id, f"💸 **طلب سحب الأرباح:**\n\nرصيدك المتاح: `{urow['balance']} TON`\nالحد الأدنى: `{bot_settings['min_withdrawal']} TON`\n\n✍ أرسل الآن الكمية التي تريد سحبها:", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
            return "OK", 200

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)