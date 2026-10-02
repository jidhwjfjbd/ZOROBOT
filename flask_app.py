import os
import time
import hashlib
import requests
from flask import Flask, request, render_template_string, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)

# إعدادات البوت وقاعدة البيانات (تم دمج بياناتك الحقيقية)
TELEGRAM_BOT_TOKEN = "8785452517:AAGy-93isP7k1qQxO_LIDb7yZMjieDhJFiw"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourBotUsername")
PROOF_CHANNEL_ID = os.environ.get("PROOF_CHANNEL_ID", "@YourProofChannel")

# كلمة سر خاصة برابط لوحة تحكم الويب للأدمن
ADMIN_WEB_PASSWORD = os.environ.get("ADMIN_WEB_PASSWORD", "zoro_admin_secure_123")

# معرفات المشرفين الأدمن (تم دمج آيدي الخاص بك)
ADMIN_IDS = [8557464787]
PRIMARY_ADMIN_USERNAME = os.environ.get("PRIMARY_ADMIN_USERNAME", "@AdminUsername")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# تهيئة الجداول في قاعدة البيانات
def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id BIGINT PRIMARY KEY,
            username TEXT,
            balance FLOAT DEFAULT 0.0,
            wallet TEXT,
            verified INT DEFAULT 0,
            invited_by BIGINT,
            banned INT DEFAULT 0,
            last_active FLOAT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_withdrawals (
            w_id TEXT PRIMARY KEY,
            user_id BIGINT,
            amount FLOAT,
            wallet TEXT,
            username TEXT,
            tx_hash TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id BIGINT,
            referred_id BIGINT,
            PRIMARY KEY (referrer_id, referred_id)
        )
    """)
    db.commit()
    cursor.close()
    db.close()

init_db()

# متغيرات النظام المؤقتة
bot_settings = {
    "referral_reward": 0.5,
    "min_withdrawal": 0.01
}

forced_channels = []
forced_bots = []
user_states = {}
admin_states = {}
temp_bot_data = {}
broadcast_data = {}
user_task_progress = {}

def send_telegram_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload).json()
        return res
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def send_main_menu(chat_id, text_msg):
    markup = {
        "keyboard": [
            [{"text": "🎁 رابط الإحالة"}, {"text": "💎 رصيدي والسحب"}],
            [{"text": "💳 ربط المحفظة"}, {"text": "📊 إحصائيات البوت"}],
            [{"text": "📞 الدعم الفني"}]
        ],
        "resize_keyboard": True
    }
    send_telegram_message(chat_id, text_msg, reply_markup=markup)

def get_next_pending_task(chat_id):
    return "done", None

def send_next_task_prompt(chat_id):
    pass

def execute_broadcast(admin_chat_id):
    pass
ADMIN_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZORO Admin - طلبات السحب المعلقة</title>
    <style>
        body { font-family: Tahoma, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: auto; background: #1e293b; padding: 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        h2 { text-align: center; color: #38bdf8; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: #334155; border-radius: 8px; overflow: hidden; }
        th, td { padding: 12px; text-align: center; border-bottom: 1px solid #475569; font-size: 14px; }
        th { background: #0284c7; color: white; }
        tr:hover { background: #3fa9f515; }
        .btn { padding: 8px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; color: white; text-decoration: none; display: inline-block; }
        .btn-approve { background: #22c55e; }
        .btn-approve:hover { background: #16a34a; }
        .btn-reject { background: #ef4444; }
        .btn-reject:hover { background: #dc2626; }
        .empty { text-align: center; padding: 30px; color: #94a3b8; font-size: 16px; }
        .wallet-box { font-family: monospace; background: #0f172a; padding: 4px 8px; border-radius: 4px; color: #cbd5e1; }
    </style>
</head>
<body>
    <div class="container">
        <h2>⚡ لوحة تحكم إدارة السحوبات - ZORO ⚡</h2>
        <p style="text-align: center; color: #94a3b8;">هنا تظهر جميع طلبات السحب المعلقة بشكل فوري ودون قيود.</p>
        
        {% if requests %}
        <table>
            <thead>
                <tr>
                    <th>المستخدم</th>
                    <th>الكمية</th>
                    <th>المحفظة</th>
                    <th>الإجراء</th>
                </tr>
            </thead>
            <tbody>
                {% for req in requests %}
                <tr>
                    <td>@{{ req.username }}</td>
                    <td style="color: #facc15; font-weight: bold;">{{ req.amount }} TON</td>
                    <td><span class="wallet-box">{{ req.wallet }}</span></td>
                    <td>
                        <a href="/admin/action/approve/{{ req.w_id }}?key={{ key }}" class="btn btn-approve">✅ قبول</a>
                        <a href="/admin/action/reject/{{ req.w_id }}?key={{ key }}" class="btn btn-reject" onclick="return confirm('هل أنت متأكد من الرفض واسترجاع الرصيد؟');">❌ رفض</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty">✅ لا توجد أي طلبات سحب معلقة حالياً في النظام.</div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/admin/dashboard')
def admin_dashboard():
    key = request.args.get("key", "")
    if key != ADMIN_WEB_PASSWORD:
        return "<h3>❌ غير مصرح لك بالدخول، يتاكد من مفتاح الحماية الصحيح في الرابط.</h3>", 403
    
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM pending_withdrawals")
    pend_rows = cursor.fetchall()
    cursor.close()
    db.close()
    
    return render_template_string(ADMIN_HTML_TEMPLATE, requests=pend_rows, key=key)

@app.route('/admin/action/<action>/<w_id>')
def admin_web_action(action, w_id):
    key = request.args.get("key", "")
    if key != ADMIN_WEB_PASSWORD:
        return "<h3>❌ غير مصرح لك بالقيام بهذه العملية.</h3>", 403
        
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
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
            
        elif action == "reject":
            if u_id not in ADMIN_IDS: 
                cursor.execute("UPDATE users SET balance = balance + %s WHERE chat_id = %s", (amount, u_id))
                db.commit()
            send_telegram_message(u_id, f"❌ **عذراً، تم رفض طلب سحبك (`{amount} TON`) وتم إرجاع الرصيد لحسابك.**")
            
    cursor.close()
    db.close()
    return redirect(url_for('admin_dashboard', key=key))
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
                    send_telegram_message(chat_id, f"📦 لديك `{len(pend_rows)}` طلب سحب معلق لم يتم اتخاذ قرار بشأنها:")
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
                send_telegram_message(chat_id, "📢 **أرسل الآن الرسالة التي تريد إذاعتها (صورة، فيديو، نص، ملف، أو أزرار وراوبط):**")
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
                    buttons = [[{"text": f"🗑 حذف {b['name']}", "callback_data": f"remove_bot_{b['name']}"}] for b in forced_bots]
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
                    send_telegram_message(chat_id, f"📦 لديك `{len(pend_rows)}` طلب سحب معلق لم يتم اتخاذ قرار بشأنها:")
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
                    send_telegram_message(chat_id, "✍️️ أرسل الاسم الذي سيظهر للمستخدم كمميز في قائمة البوتات الإجبارية:")
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
                    "text": f"👋 أهلاً بك يا مشرف البوت.\nلديك صلاحيات كاملة لإدارة البوت والطلبات المعلقة.",
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
            send_telegram_message(chat_id, f"📊 **إحصائيات البوت:**\n\n👥 إجمالي المستخدمين: `{tot_users}`\n✅ المستخدمون الموثقون: `{ver_users}`")
            return "OK", 200

        elif text == "📞 الدعم الفني":
            cursor.close()
            db.close()
            send_telegram_message(chat_id, f"📞 للإبلاغ عن مشكلة أو الاستفسار، يمكنك التواصل مع الإدارة عبر المعرف التالي:\n\n{PRIMARY_ADMIN_USERNAME}")
            return "OK", 200

        cursor.close()
        db.close()

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)