import os
import time
import hashlib
import requests
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from psycopg2.extras import RealDictCursor
import psycopg2

BOT_TOKEN = "8785452517:AAGy-93isP7k1qQxO_LIDb7yZMjieDhJFiw"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_IDS = [8667934765, 8557464787]
PRIMARY_ADMIN_USERNAME = "@m9aws"
PROOF_CHANNEL_ID = "@Proofsofbotwithdrawal"
ADMIN_CHANNEL_ID = "@YourAdminChannelID" # ضع معرف قناة المشرفين الخاصة بطلبات السحب هنا

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

forced_channels = []
forced_bots = []      
user_task_progress = {} 
admin_states = {}
user_states = {}      
temp_bot_data = {}    
broadcast_data = {}
def init_db():
    if not DATABASE_URL:
        print("⚠ تحذير: متغير DATABASE_URL غير موجود!")
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
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ تم الاتصال بقاعدة البيانات وتحديث الجداول بنجاح.")
    except Exception as e:
        print(f"❌ حدث خطأ أثناء الاتصال بقاعدة البيانات: {e}")

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

    progress = user_task_progress.setdefault(chat_id, {"channels_done": False, "bots_done": False, "bot_repeat_count": 0})

    if forced_channels:
        missing_channels = []
        for ch in forced_channels:
            clean_ch = ch.strip()
            try:
                res = requests.get(f"{TELEGRAM_API_URL}/getChatMember", params={"chat_id": clean_ch, "user_id": chat_id}).json()
                if not res.get("ok") or res["result"]["status"] not in ["creator", "administrator", "member"]:
                    missing_channels.append(clean_ch)
            except Exception:
                missing_channels.append(clean_ch)
        
        if missing_channels:
            progress["channels_done"] = False
            return "channel", missing_channels
        else:
            progress["channels_done"] = True
    else:
        progress["channels_done"] = True

    if forced_bots and not progress["bots_done"]:
        if progress.get("bot_repeat_count", 0) < 4:
            return "bots_all", forced_bots
        else:
            progress["bots_done"] = True

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
        if task_type == "channel":
            buttons = [[{"text": f"📢 انضمام إلى {ch}", "url": f"https://t.me/{ch.replace('@', '')}"}] for ch in data]
            buttons.append([{"text": "✅ تحقق من الاشتراك", "callback_data": "check_next_task"}])
            requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "⚠️ **يجب الانضمام للقنوات الإجبارية أولاً للاستمرار:**", "reply_markup": {"inline_keyboard": buttons}, "parse_mode": "Markdown"})
        elif task_type == "bots_all":
            buttons = [[{"text": f"🤖 تسجيل في بوت: {b['name']}", "url": b['url'] if b['url'].startswith('http') else f"https://t.me/{b['url'].replace('@', '')}"}] for b in data]
            buttons.append([{"text": "✅ تحقق من التسجيل", "callback_data": "click_all_bots"}])
            requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "🤖 **مهام البوتات الإجبارية:**\nسجل في البوتات ثم اضغط التحقق.", "reply_markup": {"inline_keyboard": buttons}, "parse_mode": "Markdown"})
        elif task_type == "webapp":
            render_domain = os.environ.get("RENDER_EXTERNAL_URL", "https://zorobot-qbm3.onrender.com")
            requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "🛡 **الخطوة الأخيرة:** قم بتوثيق جهازك لتنشيط الحساب:", "reply_markup": {"inline_keyboard": [[{"text": "🛡 توثيق الجهاز الآن", "web_app": {"url": render_domain}}]]}, "parse_mode": "Markdown"})
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
        return jsonify({'success': False, 'message': '🚫 حظر لمخالفة سياسة الحساب الواحد! لم تُمنح أي مكافأة.'}), 403

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
    global forced_bots, forced_channels
    update = request.get_json()
    if not update: return "OK", 200

    if "message" in update and update["message"]["chat"].get("type") in ["group", "supergroup"]:
        return "OK", 200

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id, chat_id, data = cb["id"], cb["message"]["chat"]["id"], cb.get("data", "")
        
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        if data.startswith("adm_approve_") or data.startswith("adm_reject_"):
            member_check = requests.get(f"{TELEGRAM_API_URL}/getChatMember", params={"chat_id": ADMIN_CHANNEL_ID, "user_id": chat_id}).json()
            if not member_check.get("ok") or member_check["result"]["status"] not in ["creator", "administrator"]:
                requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "Only Admin Can Do This", "show_alert": True})
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

        if chat_id in ADMIN_IDS:
            if data == "start_broadcast":
                admin_states[chat_id] = "waiting_broadcast"
                send_telegram_message(chat_id, "📢 أرسل الرسالة التي تريد إذاعتها:")
            elif data == "set_ref_reward":
                admin_states[chat_id] = "waiting_ref_reward"
                send_telegram_message(chat_id, "✍️ أدخل سعر الإحالة الجديد:")
            elif data == "set_min_withdrawal":
                admin_states[chat_id] = "waiting_min_withdrawal"
                send_telegram_message(chat_id, "✍️ أدخل الحد الأدنى للسحب:")
            elif data == "add_channel":
                admin_states[chat_id] = "waiting_add_channel"
                send_telegram_message(chat_id, "📢 أرسل معرف القناة (مثال: `@Channel`):")
            elif data == "del_channel" and forced_channels:
                buttons = [[{"text": f"🗑 {ch}", "callback_data": f"remove_ch_{ch}"}] for ch in forced_channels]
                send_telegram_message(chat_id, "اختر القناة للحذف:", reply_markup={"inline_keyboard": buttons})
            elif data.startswith("remove_ch_"):
                ch = data.replace("remove_ch_", "")
                if ch in forced_channels: forced_channels.remove(ch)
                send_telegram_message(chat_id, f"✅ تم حذف القناة `{ch}`.")
            elif data == "add_bot":
                admin_states[chat_id] = "waiting_bot_url"
                send_telegram_message(chat_id, "🤖 أرسل رابط البوت الإجباري:")
            elif data == "del_bot" and forced_bots:
                buttons = [[{"text": f"🗑 {b['name']}", "callback_data": f"remove_bot_{b['name']}"}] for b in forced_bots]
                send_telegram_message(chat_id, "اختر البوت للحذف:", reply_markup={"inline_keyboard": buttons})
            elif data.startswith("remove_bot_"):
                b_name = data.replace("remove_bot_", "")
                forced_bots[:] = [b for b in forced_bots if b['name'] != b_name]
                send_telegram_message(chat_id, "✅ تم حذف البوت.")
            elif data == "confirm_broadcast":
                execute_broadcast(chat_id)
            cursor.close(); db.close()
            return "OK", 200

        if chat_id not in ADMIN_IDS and data in ["check_next_task", "click_all_bots"]:
            if data == "click_all_bots":
                p = user_task_progress.setdefault(chat_id, {"channels_done": False, "bots_done": False, "bot_repeat_count": 0})
                p["bot_repeat_count"] = p.get("bot_repeat_count", 0) + 1
                if p["bot_repeat_count"] >= 4: p["bots_done"] = True
            cursor.close(); db.close()
            check_and_prompt_tasks(chat_id)
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
                forced_channels.append(text.strip())
                user_task_progress.clear()
                send_telegram_message(chat_id, "✅ تمت إضافة القناة بنجاح.")
            elif st == "waiting_bot_url":
                temp_bot_data[chat_id] = {"url": text.strip()}
                admin_states[chat_id] = "waiting_bot_name"
                send_telegram_message(chat_id, "أرسل اسم البوت الظاهر للمستخدم:")
            elif st == "waiting_bot_name":
                b_url = temp_bot_data.pop(chat_id, {}).get("url", "")
                forced_bots.append({"name": text.strip(), "url": b_url})
                user_task_progress.clear()
                send_telegram_message(chat_id, "✅ تمت إضافة البوت بنجاح.")
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
            send_telegram_message(chat_id, "💳 أرسل عنوان محفظة TON الخاصة بك:", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
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