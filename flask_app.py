import os
import time
import hashlib
import requests
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from psycopg2.extras import RealDictCursor
import psycopg2

BOT_TOKEN = "8785452517:AAHMx52E3En4ZBj4ZbL0BG2LRHyx9-V5nxo"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_IDS = [8667934765, 8557464787, 8162975871]
PRIMARY_ADMIN_USERNAME = "@m9aws"
PROOF_CHANNEL_ID = "@Proofsofbotwithdrawal"
ADMIN_CHANNEL_ID = "-1003509587836"

bot_settings = {
    "referral_reward": 0.01,
    "min_withdrawal": 0.01
}

BOT_USERNAME = "NeoEarnbot"
try:
    bot_info = requests.get(f"{TELEGRAM_API_URL}/getMe").json()
    if bot_info.get("ok"):
        BOT_USERNAME = bot_info["result"]["username"]
except Exception:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")

user_task_progress = {} 
admin_states = {}
user_states = {}      
temp_bot_data = {}    
broadcast_data = {}

def init_db():
    if not DATABASE_URL:
        return
    try:
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
        cursor.execute('''CREATE TABLE IF NOT EXISTS forced_channels (
                            channel_username TEXT PRIMARY KEY
                        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS forced_bots (
                            bot_name TEXT PRIMARY KEY,
                            bot_url TEXT
                        )''')
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass

def get_db():
    return psycopg2.connect(DATABASE_URL)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NeoEarnbot - نظام التحقق</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fingerprintjs2/2.1.4/fingerprint2.min.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
        .card { background: #1e293b; padding: 30px 24px; border-radius: 20px; text-align: center; width: 100%; max-width: 380px; border: 1px solid #334155; }
        .btn { background: #0284c7; color: white; border: none; padding: 14px; border-radius: 12px; font-size: 16px; font-weight: bold; width: 100%; cursor: pointer; margin-bottom: 12px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>حماية NeoEarnbot</h2>
        <p style="color: #94a3b8; font-size: 14px; margin-bottom: 20px;">قم بتأكيد بصمة جهازك لتنشيط الحساب.</p>
        <button class="btn" onclick="processVerification()">تأكيد الهوية والجهاز ✨</button>
        <div id="status" style="margin-top:15px; font-size:14px; font-weight:600;"></div>
    </div>
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        function processVerification() {
            Fingerprint2.get((components) => {
                const hash = Fingerprint2.x64hash128(components.map(p => p.value).join(''), 31);
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
def send_telegram_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)
    except Exception: pass

def get_next_pending_task(chat_id):
    if chat_id in ADMIN_IDS:
        return "done", None
        
    progress = user_task_progress.setdefault(chat_id, {"bots_done": False, "bot_clicks": 0})
    
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM forced_bots")
    forced_bots = cursor.fetchall()

    if forced_bots and not progress["bots_done"]:
        if progress["bot_clicks"] < 2:
            cursor.close(); db.close()
            return "bots_all", forced_bots
        else:
            progress["bots_done"] = True

    # جلب القنوات المعتمدة فقط من قاعدة البيانات التي أضافها الأدمن
    cursor.execute("SELECT channel_username FROM forced_channels")
    forced_channels = [row["channel_username"] for row in cursor.fetchall()]
    cursor.close()
    db.close()

    # قائمة سوداء صارمة لأي قنوات مشبوهة أو عشوائية معروفة لمنع ظهورها نهائياً
    blacklist_channels = ["@a_toolsx2", "@tucosprofit", "tucosprofit"]

    for ch in forced_channels:
        # فحص إضافي للتأكد من أن القناة ليست ضمن القائمة السوداء العشوائية
        if ch.lower().strip() in blacklist_channels or any(b in ch.lower() for b in ["tucos", "tools"]):
            continue
        try:
            res = requests.get(f"{TELEGRAM_API_URL}/getChatMember", json={"chat_id": ch, "user_id": chat_id}).json()
            status = res.get("result", {}).get("status")
            if status not in ["member", "administrator", "creator"]:
                return "channel", ch
        except Exception:
            pass

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT verified FROM users WHERE chat_id = %s", (chat_id,))
    row = cursor.fetchone()
    cursor.close()
    db.close()
    if not (row and row["verified"]):
        return "webapp", None

    return "done", None

def check_and_prompt_tasks(chat_id):
    task_type, data = get_next_pending_task(chat_id)
    if task_type != "done":
        if task_type == "bots_all":
            buttons = [[{"text": f"🤖 تسجيل في بوت: {b['bot_name']}", "url": b['bot_url'] if b['bot_url'].startswith('http') else f"https://t.me/{b['bot_url'].replace('@', '')}"}] for b in data]
            buttons.append([{"text": "✅ تحقق من التسجيل", "callback_data": "check_bots_step"}])
            requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                "chat_id": chat_id, 
                "text": "🤖 **مهام البوتات الإجبارية:**\nيجب عليك الانضمام لجميع البوتات أولاً ثم الضغط على زر التحقق مرتين لتأكيد انضمامك والاستمرار:", 
                "reply_markup": {"inline_keyboard": buttons}, 
                "parse_mode": "Markdown"
            })
        elif task_type == "channel":
            ch_link = f"https://t.me/{data.replace('@', '')}" if not data.startswith("-100") else f"https://t.me/+{data}"
            requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                "chat_id": chat_id, 
                "text": f"📢 **يجب عليك الانضمام إلى قناة البوت أولاً لتتمكن من استخدام البوت:**\n\n👉 {data}", 
                "reply_markup": {"inline_keyboard": [[{"text": "📢 انضم للقناة", "url": ch_link}], [{"text": "✅ تحققت من الانضمام", "callback_data": "check_channel"}]]}, 
                "parse_mode": "Markdown"
            })
        elif task_type == "webapp":
            render_domain = os.environ.get("RENDER_EXTERNAL_URL", "https://zorobot-qbm3.onrender.com")
            requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                "chat_id": chat_id, 
                "text": "🛡 **الخطوة الأخيرة:** قم بتوثيق جهازك لتنشيط الحساب:", 
                "reply_markup": {"inline_keyboard": [[{"text": "🛡 توثيق الجهاز الآن", "web_app": {"url": render_domain}}]]}, 
                "parse_mode": "Markdown"
            })
        return False
    return True

def execute_broadcast(admin_id):
    b_msg = broadcast_data.get(admin_id)
    if not b_msg: return
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT chat_id FROM users")
    users = cursor.fetchall()
    cursor.close()
    db.close()
    success = 0
    for u in users:
        try:
            requests.post(f"{TELEGRAM_API_URL}/copyMessage", json={"chat_id": u["chat_id"], "from_chat_id": admin_id, "message_id": b_msg})
            success += 1
        except Exception: pass
    broadcast_data.pop(admin_id, None)
    send_telegram_message(admin_id, f"📊 تمت الإذاعة بنجاح إلى `{success}` مستخدم.")

def send_main_menu(chat_id, text):
    reply_keyboard = {"keyboard": [[{"text": "🎁 رابط الإحالة"}, {"text": "💎 رصيدي والسحب"}], [{"text": "💳 ربط المحفظة"}, {"text": "📊 إحصائيات البوت"}], [{"text": "📞 الدعم الفني"}]], "resize_keyboard": True}
    if chat_id in ADMIN_IDS:
        admin_inline = {"inline_keyboard": [[{"text": "📢 إذاعة جماعية", "callback_data": "start_broadcast"}], [{"text": "💰 تعديل الإحالة", "callback_data": "set_ref_reward"}, {"text": "💸 تعديل السحب", "callback_data": "set_min_withdrawal"}], [{"text": "📢 إضافة قناة", "callback_data": "add_channel"}, {"text": "🗑 حذف قناة", "callback_data": "del_channel"}], [{"text": "🤖 إضافة بوت", "callback_data": "add_bot"}, {"text": "🗑️ حذف بوت", "callback_data": "del_bot"}]]}
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "📂 **لوحة التحكم الإدارية:**", "parse_mode": "Markdown", "reply_markup": admin_inline})
    send_telegram_message(chat_id, text, reply_markup=reply_keyboard)

app = Flask(__name__)
init_db()
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json or {}
    user_id, fingerprint = data.get('user_id'), data.get('fingerprint')
    if not user_id or not fingerprint: return jsonify({'success': False}), 400
    try: user_id = int(user_id)
    except ValueError: pass

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT banned FROM users WHERE chat_id = %s", (user_id,))
    row = cursor.fetchone()
    if row and row["banned"] == 1:
        cursor.close(); db.close()
        return jsonify({'success': False, 'message': '🚫 محظور!'}), 403

    cursor.execute("INSERT INTO users (chat_id, balance, verified, banned, last_active) VALUES (%s, 0.0, 0, 0, %s) ON CONFLICT (chat_id) DO UPDATE SET last_active = EXCLUDED.last_active", (user_id, time.time()))
    db.commit()

    if user_id in ADMIN_IDS:
        cursor.execute("UPDATE users SET verified = 1 WHERE chat_id = %s", (user_id,))
        db.commit(); cursor.close(); db.close()
        return jsonify({'success': True})

    cursor.execute("SELECT chat_id FROM fingerprints WHERE fingerprint = %s", (fingerprint,))
    f_row = cursor.fetchone()
    if f_row and f_row["chat_id"] != user_id:
        cursor.execute("UPDATE users SET banned = 1 WHERE chat_id = %s", (user_id,))
        db.commit(); cursor.close(); db.close()
        return jsonify({'success': False, 'message': '🚫 حظر لمخالفة سياسة الحساب الواحد!'}), 403

    cursor.execute("INSERT INTO fingerprints (fingerprint, chat_id) VALUES (%s, %s) ON CONFLICT (fingerprint) DO UPDATE SET chat_id = EXCLUDED.chat_id", (fingerprint, user_id))
    db.commit()

    cursor.execute("UPDATE users SET verified = 1 WHERE chat_id = %s", (user_id,))
    cursor.execute("SELECT invited_by FROM users WHERE chat_id = %s", (user_id,))
    u_row = cursor.fetchone()
    db.commit()

    if u_row and u_row["invited_by"] and u_row["invited_by"] != user_id:
        ref_id = u_row["invited_by"]
        cursor.execute("SELECT 1 FROM referrals WHERE referrer_id = %s AND referred_id = %s", (ref_id, user_id))
        if not cursor.fetchone():
            reward = bot_settings["referral_reward"]
            cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id = %s", (reward, ref_id))
            cursor.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (ref_id, user_id))
            db.commit()
            send_telegram_message(ref_id, f"🎉 مستخدم جديد انضم عبر رابطك وأتم التحقق! حصلت على `{reward} TON`.")

    cursor.close(); db.close()
    return jsonify({'success': True})
@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if not update: return "OK", 200

    if "message" in update and update["message"]["chat"].get("type") in ["group", "supergroup"]:
        return "OK", 200

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id, chat_id, data = cb["id"], cb["message"]["chat"]["id"], cb.get("data", "")
        user_who_clicked = cb["from"]["id"]
        
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        if data == "check_bots_step":
            prog = user_task_progress.setdefault(user_who_clicked, {"bots_done": False, "bot_clicks": 0})
            prog["bot_clicks"] += 1
            if prog["bot_clicks"] == 1:
                requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "⚠️ يرجى التأكد من الانضمام لجميع البوتات أولاً ثم اضغط تحقق مرة أخرى!", "show_alert": True})
            else:
                prog["bots_done"] = True
                requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "✅ تم التحقق بنجاح!"})
            
            try:
                requests.post(f"{TELEGRAM_API_URL}/deleteMessage", json={"chat_id": user_who_clicked, "message_id": cb["message"]["message_id"]})
            except Exception:
                pass
            
            cursor.close(); db.close()
            if check_and_prompt_tasks(user_who_clicked):
                send_main_menu(user_who_clicked, "✨ أهلاً بك في القائمة الرئيسية:")
            return "OK", 200

        if data == "check_channel":
            requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "جاري التحقق..."})
            try:
                requests.post(f"{TELEGRAM_API_URL}/deleteMessage", json={"chat_id": user_who_clicked, "message_id": cb["message"]["message_id"]})
            except Exception:
                pass
            cursor.close(); db.close()
            if check_and_prompt_tasks(user_who_clicked):
                send_main_menu(user_who_clicked, "✨ أهلاً بك في القائمة الرئيسية:")
            return "OK", 200

        if data.startswith("adm_approve_") or data.startswith("adm_reject_"):
            if user_who_clicked not in ADMIN_IDS:
                requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "هذا الزر مخصص للأدمن فقط!", "show_alert": True})
                cursor.close(); db.close()
                return "OK", 200

            action = "approve" if "approve" in data else "reject"
            w_id = data.replace("adm_approve_", "").replace("adm_reject_", "")

            cursor.execute("SELECT * FROM pending_withdrawals WHERE w_id = %s", (w_id,))
            w_row = cursor.fetchone()
            if not w_row:
                requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "الطلب غير موجود أو تم معالجته مسبقاً!", "show_alert": True})
                cursor.close(); db.close()
                return "OK", 200

            u_id, amount, wallet, username, tx_hash = w_row["user_id"], w_row["amount"], w_row["wallet"], w_row["username"], w_row["tx_hash"]
            cursor.execute("DELETE FROM pending_withdrawals WHERE w_id = %s", (w_id,))
            db.commit()

            if action == "approve":
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                proof_text = f"💎 **Payment Successful!**\n👤 المستخدم: @{username}\n💵 الكمية: `{amount}` TON\n📥 المحفظة: `{wallet}`\n⏰ التوقيت: `{time_str}`"
                requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": PROOF_CHANNEL_ID, "text": proof_text, "parse_mode": "Markdown"})
                send_telegram_message(u_id, f"🎉 **تم قبول طلب سحبك بنجاح!**\n💵 الكمية: `{amount} TON`")
                new_text = cb["message"]["text"] + f"\n\n✅ **Approved by Admin**"
            else:
                if u_id not in ADMIN_IDS:
                    cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id = %s", (amount, u_id))
                    db.commit()
                send_telegram_message(u_id, f"❌ **عذراً، تم رفض طلب سحبك (`{amount} TON`) وإعادة الرصيد.**")
                new_text = cb["message"]["text"] + f"\n\n❌ **Rejected by Admin**"

            requests.post(f"{TELEGRAM_API_URL}/editMessageText", json={"chat_id": chat_id, "message_id": cb["message"]["message_id"], "text": new_text, "parse_mode": "Markdown"})
            requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "تمت العملية بنجاح"})
            cursor.close(); db.close()
            return "OK", 200

        try: requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id})
        except Exception: pass

        if user_who_clicked in ADMIN_IDS:
            if data == "start_broadcast":
                admin_states[user_who_clicked] = "waiting_broadcast"
                send_telegram_message(user_who_clicked, "📢 أرسل الرسالة التي تريد إذاعتها:")
            elif data == "set_ref_reward":
                admin_states[user_who_clicked] = "waiting_ref_reward"
                send_telegram_message(user_who_clicked, "✍ أدخل سعر الإحالة الجديد:")
            elif data == "set_min_withdrawal":
                admin_states[user_who_clicked] = "waiting_min_withdrawal"
                send_telegram_message(user_who_clicked, "✍️ أدخل الحد الأدنى للسحب:")
            elif data == "add_channel":
                admin_states[user_who_clicked] = "waiting_add_channel"
                send_telegram_message(user_who_clicked, "📢 أرسل معرف القناة (مثال: `@Channel`):")
            elif data == "del_channel":
                cursor.execute("SELECT channel_username FROM forced_channels")
                ch_rows = cursor.fetchall()
                if ch_rows:
                    buttons = [[{"text": f"🗑 {r['channel_username']}", "callback_data": f"remove_ch_{r['channel_username']}"}] for r in ch_rows]
                    send_telegram_message(user_who_clicked, "اختر القناة للحذف:", reply_markup={"inline_keyboard": buttons})
                else:
                    send_telegram_message(user_who_clicked, "⚠ لا توجد قنوات مسجلة حالياً.")
            elif data.startswith("remove_ch_"):
                ch = data.replace("remove_ch_", "")
                cursor.execute("DELETE FROM forced_channels WHERE channel_username = %s", (ch,))
                db.commit()
                send_telegram_message(user_who_clicked, f"✅ تم حذف القناة `{ch}`.")
            elif data == "add_bot":
                admin_states[user_who_clicked] = "waiting_bot_url"
                send_telegram_message(user_who_clicked, "🤖 أرسل رابط البوت الإجباري:")
            elif data == "del_bot":
                cursor.execute("SELECT bot_name FROM forced_bots")
                b_rows = cursor.fetchall()
                if b_rows:
                    buttons = [[{"text": f"🗑 {r['bot_name']}", "callback_data": f"remove_bot_{r['bot_name']}"}] for r in b_rows]
                    send_telegram_message(user_who_clicked, "اختر البوت للحذف:", reply_markup={"inline_keyboard": buttons})
                else:
                    send_telegram_message(user_who_clicked, "⚠️ لا توجد بوتات مسجلة حالياً.")
            elif data.startswith("remove_bot_"):
                b_name = data.replace("remove_bot_", "")
                cursor.execute("DELETE FROM forced_bots WHERE bot_name = %s", (b_name,))
                db.commit()
                send_telegram_message(user_who_clicked, "✅ تم حذف البوت.")
            elif data == "confirm_broadcast":
                execute_broadcast(user_who_clicked)
            cursor.close(); db.close()
            return "OK", 200

        cursor.close(); db.close()
        return "OK", 200
    if "message" in update:
        msg = update["message"]
        chat_id, text = msg["chat"]["id"], msg.get("text", "")
        username = msg["from"].get("username") or f"user_{chat_id}"

        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        cursor.execute("INSERT INTO users (chat_id, username, balance, verified, banned, last_active) VALUES (%s, %s, 0.0, 0, 0, %s) ON CONFLICT (chat_id) DO UPDATE SET username = EXCLUDED.username, last_active = EXCLUDED.last_active", (chat_id, username, time.time()))
        db.commit()

        if text.startswith("/start"):
            parts = text.split(" ")
            if len(parts) > 1 and parts[1].isdigit():
                ref_id = int(parts[1])
                if ref_id != chat_id and chat_id not in ADMIN_IDS:
                    cursor.execute("SELECT invited_by, verified FROM users WHERE chat_id = %s", (chat_id,))
                    r_chk = cursor.fetchone()
                    if r_chk and not r_chk["invited_by"] and not r_chk["verified"]:
                        cursor.execute("UPDATE users SET invited_by = %s WHERE chat_id = %s", (ref_id, chat_id))
                        db.commit()

            cursor.close(); db.close()
            if not check_and_prompt_tasks(chat_id):
                return "OK", 200
            send_main_menu(chat_id, "✨ أهلاً بك مجدداً في بوت NeoEarnbot ⚡")
            return "OK", 200

        if not check_and_prompt_tasks(chat_id):
            cursor.close(); db.close()
            return "OK", 200

        if text == "🔙 العودة للقائمة الرئيسية":
            user_states.pop(chat_id, None); admin_states.pop(chat_id, None)
            cursor.close(); db.close()
            send_main_menu(chat_id, "🔙 العودة للقائمة الرئيسية:")
            return "OK", 200

        if chat_id in ADMIN_IDS and chat_id in admin_states:
            st = admin_states.pop(chat_id)
            if st == "waiting_broadcast":
                broadcast_data[chat_id] = msg["message_id"]
                send_telegram_message(chat_id, "تأكيد الإذاعة لجميع المستخدمين؟", reply_markup={"inline_keyboard": [[{"text": "🚀 إرسال الآن", "callback_data": "confirm_broadcast"}]]})
            elif st == "waiting_ref_reward":
                bot_settings["referral_reward"] = float(text.strip())
                send_telegram_message(chat_id, "✅ تم تحديث مكافأة الإحالة.")
            elif st == "waiting_min_withdrawal":
                bot_settings["min_withdrawal"] = float(text.strip())
                send_telegram_message(chat_id, "✅ تم تحديث الحد الأدنى للسحب.")
            elif st == "waiting_add_channel":
                channel_input = text.strip()
                
                # 🛑 شرط حماية صارم يمنع إضافة @tucosprofit أو أي قناة عشوائية مشابهة تلقائياً
                if any(bad in channel_input.lower() for bad in ["tucos", "tools", "a_tools"]):
                    send_telegram_message(chat_id, "❌ عذراً، هذه القناة محظورة برمجياً ولا يمكن إضافتها نهائياً.")
                    cursor.close(); db.close()
                    return "OK", 200

                cursor.execute("INSERT INTO forced_channels (channel_username) VALUES (%s) ON CONFLICT DO NOTHING", (channel_input,))
                db.commit()
                user_task_progress.clear()
                send_telegram_message(chat_id, "✅ تمت إضافة القناة بنجاح في قاعدة البيانات.")
            elif st == "waiting_bot_url":
                temp_bot_data[chat_id] = {"url": text.strip()}
                admin_states[chat_id] = "waiting_bot_name"
                send_telegram_message(chat_id, "أرسل اسم البوت الظاهر للمستخدم:")
            elif st == "waiting_bot_name":
                b_url = temp_bot_data.pop(chat_id, {}).get("url", "")
                b_name = text.strip()
                cursor.execute("INSERT INTO forced_bots (bot_name, bot_url) VALUES (%s, %s) ON CONFLICT (bot_name) DO UPDATE SET bot_url = EXCLUDED.bot_url", (b_name, b_url))
                db.commit()
                user_task_progress.clear()
                send_telegram_message(chat_id, "✅ تمت إضافة البوت بنجاح في قاعدة البيانات.")
            cursor.close(); db.close()
            return "OK", 200
        if chat_id in user_states:
            st = user_states.pop(chat_id)
            if st == "waiting_wallet":
                cursor.execute("UPDATE users SET wallet = %s WHERE chat_id = %s", (text.strip(), chat_id))
                db.commit(); cursor.close(); db.close()
                send_telegram_message(chat_id, "✅ تم حفظ المحفظة بنجاح!")
                send_main_menu(chat_id, "القائمة الرئيسية:")
                return "OK", 200
            elif st == "waiting_withdraw_amount":
                try: amount = float(text.strip())
                except ValueError:
                    user_states[chat_id] = "waiting_withdraw_amount"
                    cursor.close(); db.close()
                    send_telegram_message(chat_id, "❌ يرجى إدخال رقم صحيح كمية السحب:")
                    return "OK", 200

                cursor.execute("SELECT balance, wallet FROM users WHERE chat_id = %s", (chat_id,))
                urow = cursor.fetchone()
                if not urow or not urow["wallet"]:
                    cursor.close(); db.close()
                    send_telegram_message(chat_id, "⚠️ يرجى ربط المحفظة أولاً.")
                    return "OK", 200

                if amount < bot_settings["min_withdrawal"] or amount > urow["balance"]:
                    user_states[chat_id] = "waiting_withdraw_amount"
                    cursor.close(); db.close()
                    send_telegram_message(chat_id, "❌ عذراً، الكمية غير صالحة أو الرصيد غير كافٍ.")
                    return "OK", 200

                cursor.execute("UPDATE users SET balance = balance - %s WHERE chat_id = %s", (amount, chat_id))
                db.commit()
                w_id = hashlib.md5(f"{chat_id}_{time.time()}".encode()).hexdigest()[:10]
                tx_hash = hashlib.sha256(f"{w_id}_{amount}".encode()).hexdigest()[:24]
                cursor.execute("INSERT INTO pending_withdrawals VALUES (%s, %s, %s, %s, %s, %s)", (w_id, chat_id, amount, urow["wallet"], username, tx_hash))
                db.commit()

                admin_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Approve", "callback_data": f"adm_approve_{w_id}"},
                            {"text": "❌ Reject", "callback_data": f"adm_reject_{w_id}"}
                        ]
                    ]
                }
                withdrawal_text = f"💎 **New Payout Request**\n\n📌 User : `{chat_id}` (@{username})\n💵 Amount : `{amount} TON`\n📥 Send To (Address): `{urow['wallet']}`\n📄 Transaction ID:\n`{tx_hash}`"
                requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": ADMIN_CHANNEL_ID, "text": withdrawal_text, "parse_mode": "Markdown", "reply_markup": admin_markup})

                cursor.close(); db.close()
                send_telegram_message(chat_id, f"✅ **تم إرسال طلب السحب (`{amount} TON`) بنجاح وهو قيد المراجعة من الإدارة.**")
                send_main_menu(chat_id, "القائمة الرئيسية:")
                return "OK", 200

        if text == "🎁 رابط الإحالة":
            ref_link = f"https://t.me/{BOT_USERNAME}?start={chat_id}"
            cursor.execute("SELECT COUNT(*) as count FROM referrals WHERE referrer_id = %s", (chat_id,))
            cnt = cursor.fetchone()["count"]
            cursor.close(); db.close()
            send_telegram_message(chat_id, f"🎁 **نظام الإحالات:**\n\n🔗 رابطك:\n`{ref_link}`\n\n👥 عدد المدعوين: `{cnt}`")
            return "OK", 200

        elif text == "💎 رصيدي والسحب":
            cursor.execute("SELECT balance, wallet FROM users WHERE chat_id = %s", (chat_id,))
            urow = cursor.fetchone()
            cursor.close(); db.close()
            if not urow or not urow["wallet"]:
                send_telegram_message(chat_id, "⚠️ ربط المحفظة مطلوب أولاً.")
                return "OK", 200
            if urow["balance"] < bot_settings["min_withdrawal"]:
                send_telegram_message(chat_id, f"❌ رصيدك أقل من الحد الأدنى (`{bot_settings['min_withdrawal']} TON`).")
                return "OK", 200
            user_states[chat_id] = "waiting_withdraw_amount"
            send_telegram_message(chat_id, f"💸 رصيدك المتاح: `{urow['balance']} TON`\n✍️ أرسل كمية السحب:", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
            return "OK", 200

        elif text == "💳 ربط المحفظة":
            user_states[chat_id] = "waiting_wallet"
            cursor.close(); db.close()
            send_telegram_message(chat_id, f"💳 أرسل عنوان محفظة TON الخاصة بك:", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
            return "OK", 200

        elif text == "📊 إحصائيات البوت":
            cursor.execute("SELECT COUNT(*) as tot FROM users")
            tot = cursor.fetchone()["tot"]
            cursor.execute("SELECT COUNT(*) as ver FROM users WHERE verified = 1")
            ver = cursor.fetchone()["ver"]
            cursor.close(); db.close()
            send_telegram_message(chat_id, f"📊 الإحصائيات:\n👥 الإجمالي: `{tot}`\n✅ الموثقون: `{ver}`")
            return "OK", 200

        elif text == "📞 الدعم الفني":
            cursor.close(); db.close()
            send_telegram_message(chat_id, f"📞 للتواصل مع الإدارة:\n{PRIMARY_ADMIN_USERNAME}")
            return "OK", 200

        cursor.close(); db.close()

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)