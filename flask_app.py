import os
import requests
import time
import hashlib
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

BOT_TOKEN = "8785452517:AAGy-93isP7k1qQxO_LIDb7yZMjieDhJFiw"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_IDS = [8667934765, 8557464787]
PRIMARY_ADMIN_USERNAME = "@sig2siel"
PROOF_CHANNEL_ID = "@Proofsofbotwithdrawal"

bot_settings = {
    "referral_reward": 0.10,
    "min_withdrawal": 1.00
}

app = Flask(__name__)

BOT_USERNAME = "ZoroBot"
try:
    bot_info = requests.get(f"{TELEGRAM_API_URL}/getMe").json()
    if bot_info.get("ok"):
        BOT_USERNAME = bot_info["result"]["username"]
except Exception:
    pass

registered_fingerprints = {}
verified_users = set()
banned_users = set()
all_bot_users = set()
user_balances = {}
user_wallets = {}
user_referrals = {}
invited_by = {}
pending_withdrawals = {}
user_has_pending = set()
user_last_active = {}
withdrawal_counter = 0

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

def get_next_pending_task(chat_id):
    if chat_id in ADMIN_IDS:
        return "done", None

    progress = user_task_progress.setdefault(chat_id, {"channels_done": False, "bot_idx": 0, "bot_repeat_count": 0, "bot_clicks": {}})

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

    if forced_bots and progress["bot_idx"] < len(forced_bots):
        b_idx = progress["bot_idx"]
        current_bot = forced_bots[b_idx]
        repeat_target = current_bot.get("repeat_target", 3) 
        current_repeats = progress.get("bot_repeat_count", 0)
        
        if current_repeats < repeat_target:
            return "bot", {"bot": current_bot, "idx": b_idx, "current": current_repeats + 1, "total": repeat_target}

    if chat_id not in verified_users:
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

    elif task_type == "bot":
        b_info = data["bot"]
        b_idx = data["idx"]
        bot_url = b_info["url"]
        if not bot_url.startswith("http"):
            bot_url = f"https://t.me/{b_info['url'].replace('@', '')}"
        
        buttons = [
            [{"text": f"🤖 تسجيل في بوت: {b_info['name']}", "url": bot_url}],
            [{"text": "✅ تحقق من التسجيل", "callback_data": f"click_bot_{b_idx}"}]
        ]
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": f"🤖 **مهمة البوت ({data['current']}/{data['total']}):**\n\nيجب التسجيل في البوت أولاً ثم الضغط على زر التحقق.", "reply_markup": {"inline_keyboard": buttons}, "parse_mode": "Markdown"})

    elif task_type == "webapp":
        render_domain = os.environ.get("RENDER_EXTERNAL_URL", "https://zorobot-qbm3.onrender.com")
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "🛡 **الخطوة الأخيرة:** قم بتوثيق جهازك عبر زر الأمان أدناه لتنشيط الحساب:", "reply_markup": {"inline_keyboard": [[{"text": "🛡 توثيق الجهاز الآن (ZORO)", "web_app": {"url": render_domain}}]]}, "parse_mode": "Markdown"})

    elif task_type == "done":
        if chat_id not in verified_users and chat_id not in ADMIN_IDS:
            verified_users.add(chat_id)
            if chat_id in invited_by:
                referrer_id = invited_by[chat_id]
                if referrer_id != chat_id and chat_id not in user_referrals.get(referrer_id, []):
                    reward = bot_settings["referral_reward"]
                    user_balances[referrer_id] = user_balances.get(referrer_id, 0.0) + reward
                    user_referrals.setdefault(referrer_id, []).append(chat_id)
                    new_user_username = user_task_progress.get(chat_id, {}).get("username", "مستخدم جديد")
                    send_telegram_message(referrer_id, f"🎉 سجل @{new_user_username} الدخول للبوت عبر رابطك واجتاز شروط التحقق والمهام بنجاح! حصلت على `{reward} TON`.")
        
        send_main_menu(chat_id, "✨ تمت كافة خطوات التحقق بنجاح وأصبح حسابك مفعلاً بالكامل!")

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
    has_pending = True if (forced_channels or forced_bots) and t_type in ["channel", "bot"] else False
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
    if user_id in banned_users: 
        return jsonify({'success': False, 'message': '🚫 محظور!'}), 403
    
    all_bot_users.add(user_id)
    user_last_active[user_id] = time.time()

    if user_id in ADMIN_IDS:
        verified_users.add(user_id)
        return jsonify({'success': True})

    if fingerprint in registered_fingerprints and registered_fingerprints[fingerprint] != user_id:
        banned_users.add(user_id)
        return jsonify({'success': False, 'message': '🚫 تم حظرك نهائياً لمخالفة سياسة الحساب الواحد!'}), 403
    
    registered_fingerprints[fingerprint] = user_id
    
    if forced_channels or forced_bots:
        task_type, _ = get_next_pending_task(user_id)
        if task_type != "done" and task_type != "webapp":
            return jsonify({'success': False, 'message': '⚠️ يجب إكمال القنوات والبوتات أولاً!'}), 400

    verified_users.add(user_id)
    
    if chat_id_in_referral := invited_by.get(user_id):
        if chat_id_in_referral != user_id and user_id not in user_referrals.get(chat_id_in_referral, []):
            reward = bot_settings["referral_reward"]
            user_balances[chat_id_in_referral] = user_balances.get(chat_id_in_referral, 0.0) + reward
            user_referrals.setdefault(chat_id_in_referral, []).append(user_id)
            send_telegram_message(chat_id_in_referral, f"🎉 شخص ما انضم عبر رابط إحالتك وأتم التحقق بنجاح! حصلت على `{reward} TON`.")

    return jsonify({'success': True})
def execute_broadcast(admin_id):
    b_msg = broadcast_data.get(admin_id)
    if not b_msg: 
        return
    success = 0
    for uid in list(all_bot_users):
        try:
            # نسخ الرسالة الأصلية المرسلة من الأدمن مباشرة بكل محتوياتها (صور، فيديوهات، نصوص، ملفات...) إلى المستخدمين
            res = requests.post(f"{TELEGRAM_API_URL}/copyMessage", json={
                "chat_id": uid,
                "from_chat_id": admin_id,
                "message_id": b_msg
            })
            if res.json().get("ok"):
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
    global forced_bots, forced_channels, withdrawal_counter
    update = request.get_json()
    if not update: 
        return "OK", 200

    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id, chat_id, msg_id, data = cb["id"], cb["message"]["chat"]["id"], cb["message"]["message_id"], cb.get("data", "")
        try: 
            requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb_id})
        except Exception: 
            pass

        if chat_id in ADMIN_IDS:
            if data.startswith("approve_w_") or data.startswith("reject_w_"):
                parts = data.split("_")
                action, w_id = parts[0], parts[2]
                if w_id in pending_withdrawals:
                    w_data = pending_withdrawals.pop(w_id)
                    u_id, amount, wallet, username, tx_hash = w_data["user_id"], w_data["amount"], w_data["wallet"], w_data["username"], w_data["tx_hash"]
                    user_has_pending.discard(u_id)
                    if action == "approve":
                        withdrawal_counter += 1
                        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        proof_text = f"💎 **Gram Payment Successful!**\n\n🔢 **السحب رقم:** (`{withdrawal_counter}`)\n👤 المستخدم: @{username}\n💵 الكمية: `{amount}` TON\n📥 المحفظة: `{wallet}`\n⏰ التوقيت: `{current_time_str}`\n🔗 TX: `{tx_hash}`\n■ Status: ✅ Successful"
                        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": PROOF_CHANNEL_ID, "text": proof_text, "parse_mode": "Markdown"})
                        
                        user_success_msg = f"🎉 **تم قبول طلب السحب الخاص بك بنجاح!**\n\n🔢 رقم السحب: `{withdrawal_counter}`\n👤 اليوزر: @{username}\n💵 الكمية: `{amount} TON`\n⏰ التوقيت: `{current_time_str}`"
                        send_telegram_message(u_id, user_success_msg)
                        
                        requests.post(f"{TELEGRAM_API_URL}/editMessageText", json={"chat_id": chat_id, "message_id": msg_id, "text": f"✅ **تم قبول السحب ونشره في القناة برقم ({withdrawal_counter}):**\n\n{proof_text}", "parse_mode": "Markdown"})
                    elif action == "reject":
                        if u_id not in ADMIN_IDS: 
                            user_balances[u_id] = user_balances.get(u_id, 0.0) + amount
                        send_telegram_message(u_id, f"❌ **عذراً، تم رفض طلب سحبك (`{amount} TON`) وتم إرجاع الرصيد لحسابك.**")
                        requests.post(f"{TELEGRAM_API_URL}/editMessageText", json={"chat_id": chat_id, "message_id": msg_id, "text": "❌ **تم رفض الطلب واسترجاع الرصيد.**", "parse_mode": "Markdown"})
                return "OK", 200

            if data == "start_broadcast":
                admin_states[chat_id] = "waiting_broadcast"
                send_telegram_message(chat_id, "📢 أرسل الآن المنشور المراد إذاعته (يمكنك إرسال: نص، صورة، فيديو، ملف، أو أي شيء مع التنسيق):")
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
                    send_telegram_message(chat_id, "⚠️ لا توجد بوتات مسجلة.")
                else:
                    buttons = [[{"text": f"🗑️ حذف {b['name']}", "callback_data": f"remove_bot_{b['name']}"}] for b in forced_bots]
                    send_telegram_message(chat_id, "🗑 اختر البوت المراد حذفه:", reply_markup={"inline_keyboard": buttons})
            elif data.startswith("remove_bot_"):
                b_name_del = data.replace("remove_bot_", "")
                forced_bots[:] = [b for b in forced_bots if b['name'] != b_name_del]
                send_telegram_message(chat_id, f"✅ تم حذف البوت بنجاح.")
            elif data == "confirm_broadcast":
                execute_broadcast(chat_id)
            return "OK", 200

        if chat_id not in ADMIN_IDS and data == "check_next_task":
            send_next_task_prompt(chat_id)
            return "OK", 200

        if chat_id not in ADMIN_IDS and data.startswith("click_bot_"):
            b_idx = int(data.replace("click_bot_", ""))
            progress = user_task_progress.setdefault(chat_id, {"channels_done": False, "bot_idx": 0, "bot_repeat_count": 0, "bot_clicks": {}})
            
            progress["bot_repeat_count"] = progress.get("bot_repeat_count", 0) + 1
            current_bot = forced_bots[b_idx]
            target_repeats = current_bot.get("repeat_target", 3)
            
            if progress["bot_repeat_count"] >= target_repeats:
                progress["bot_idx"] += 1
                progress["bot_repeat_count"] = 0
            
            send_next_task_prompt(chat_id)
            return "OK", 200

        return "OK", 200

    if "message" in update:
        msg = update["message"]
        chat_id, text = msg["chat"]["id"], msg.get("text", "")
        username = msg["from"].get("username") or f"user_{chat_id}"
        all_bot_users.add(chat_id)
        user_last_active[chat_id] = time.time()
        
        user_task_progress.setdefault(chat_id, {"channels_done": False, "bot_idx": 0, "bot_repeat_count": 0, "bot_clicks": {}})["username"] = username

        if text == "🔙 العودة للقائمة الرئيسية":
            user_states.pop(chat_id, None)
            admin_states.pop(chat_id, None)
            task_type, _ = get_next_pending_task(chat_id)
            if task_type != "done":
                send_next_task_prompt(chat_id)
            else:
                send_main_menu(chat_id, "🔙 تم العودة للقائمة الرئيسية:")
            return "OK", 200

        if chat_id in ADMIN_IDS and chat_id in admin_states:
            state = admin_states[chat_id]
            if state == "waiting_broadcast":
                admin_states.pop(chat_id, None)
                broadcast_data[chat_id] = msg["message_id"] # حفظ معرف رسالة الأدمن أياً كانت (صورة، نص، فيديو...)
                
                # معاينة سريعة للأدمن للتأكيد
                requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                    "chat_id": chat_id, 
                    "text": "📌 معاينة الرسالة المراد إرسالها بالأعلى.\nهل تريد تأكيد إرسالها لجميع المستخدمين؟",
                    "reply_markup": {"inline_keyboard": [[{"text": "🚀 إرسال الآن", "callback_data": "confirm_broadcast"}]]}
                })
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
                forced_bots.append({"name": b_name, "url": b_url, "repeat_target": 3})
                user_task_progress.clear()
                send_telegram_message(chat_id, f"✅ تم إضافة البوت `{b_name}` بنجاح ليظهر لجميع المستخدمين.")
            return "OK", 200

        if chat_id in user_states:
            state = user_states.pop(chat_id, None)
            if state == "waiting_wallet":
                user_wallets[chat_id] = text.strip()
                send_main_menu(chat_id, f"✅ تم حفظ محفظة TON:\n`{text.strip()}`")
            elif state == "waiting_withdrawal_amount":
                if chat_id in user_has_pending:
                    send_main_menu(chat_id, "⚠ لديك طلب سحب قيد المراجعة بالفعل.")
                else:
                    try:
                        amount = float(text.strip())
                        bal = 999999.0 if chat_id in ADMIN_IDS else user_balances.get(chat_id, 0.0)
                        if amount < bot_settings["min_withdrawal"] or amount > bal:
                            send_main_menu(chat_id, f"❌ المبلغ غير صالح أو أقل من الحد الأدنى (`{bot_settings['min_withdrawal']} TON`) أو رصيدك لا يكفي.")
                        else:
                            wallet = user_wallets.get(chat_id)
                            if not wallet: 
                                send_main_menu(chat_id, "⚠️ يجب ربط محفظة TON أولاً!")
                            else:
                                if chat_id not in ADMIN_IDS: 
                                    user_balances[chat_id] = bal - amount
                                user_has_pending.add(chat_id)
                                w_id = str(int(time.time())) + str(chat_id)[-4:]
                                tx_hash = hashlib.sha256(w_id.encode()).hexdigest()[:32]
                                pending_withdrawals[w_id] = {"user_id": chat_id, "amount": amount, "wallet": wallet, "username": username, "tx_hash": tx_hash}
                                kb = {"inline_keyboard": [[{"text": "✅ قبول", "callback_data": f"approve_w_{w_id}"}, {"text": "❌ رفض", "callback_data": f"reject_w_{w_id}"}]]}
                                for aid in ADMIN_IDS:
                                    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": aid, "text": f"💸 طلب سحب جديد:\n👤 User: @{username}\n💎 Amount: `{amount} TON`\n💳 Wallet: `{wallet}`", "reply_markup": kb, "parse_mode": "Markdown"})
                                send_main_menu(chat_id, f"🎉 تم تقديم طلب السحب بنجاح بقيمة `{amount} TON` وهو قيد المراجعة.")
                    except ValueError: 
                        send_main_menu(chat_id, "❌ قيمة غير صالحة.")
            return "OK", 200

        if text.startswith("/start"):
            parts = text.split()
            if len(parts) > 1 and parts[1].isdigit():
                ref_id = int(parts[1])
                if ref_id != chat_id and chat_id not in invited_by: 
                    invited_by[chat_id] = ref_id
            
            task_type, _ = get_next_pending_task(chat_id)
            if task_type != "done":
                send_next_task_prompt(chat_id)
                return "OK", 200

            if chat_id in ADMIN_IDS or chat_id in verified_users:
                send_main_menu(chat_id, "أهلاً بك مجدداً 👋")
            else:
                send_next_task_prompt(chat_id)
            return "OK", 200

        if chat_id not in ADMIN_IDS:
            task_type, _ = get_next_pending_task(chat_id)
            if task_type != "done": 
                send_next_task_prompt(chat_id)
                return "OK", 200

        if text == "🎁 رابط الإحالة":
            reward_val = bot_settings["referral_reward"]
            send_main_menu(chat_id, f"🎁 رابط الإحالة الخاص بك:\n`https://t.me/{BOT_USERNAME}?start={chat_id}`\n\n💰 **سعر الإحالة:** `{reward_val} TON` لكل شخص يقوم بالانضمام وتخطّي المهام والتحقق الكامل.\nعدد إحالاتك الناجحة: `{len(user_referrals.get(chat_id, []))}`")
        elif text == "💎 رصيدي والسحب":
            bal = 999999.0 if chat_id in ADMIN_IDS else user_balances.get(chat_id, 0.0)
            min_w = bot_settings["min_withdrawal"]
            user_states[chat_id] = "waiting_withdrawal_amount"
            send_telegram_message(chat_id, f"💎 رصيدك الحالي: `{bal:.2f} TON`\n⚠️ **الحد الأدنى للسحب هو:** `{min_w} TON`\n\n✍️ أدخل المبلغ المراد سحبه الآن:", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
        elif text == "💳 ربط المحفظة":
            user_states[chat_id] = "waiting_wallet"
            send_telegram_message(chat_id, f"💳 أرسل عنوان محفظة TON الخاصة بك:", reply_markup={"keyboard": [[{"text": "🔙 العودة للقائمة الرئيسية"}]], "resize_keyboard": True})
        elif text == "📊 إحصائيات البوت":
            total_users = len(all_bot_users)
            sorted_refs = sorted(user_referrals.items(), key=lambda x: len(x[1]), reverse=True)[:5]
            top_text = ""
            for idx, (uid, refs) in enumerate(sorted_refs, 1):
                top_text += f"{idx}. مستخدم بمعرف (`{uid}`) - عدد الإحالات: `{len(refs)}`\n"
            if not top_text:
                top_text = "لا توجد إحالات مسجلة بعد."

            if chat_id in ADMIN_IDS:
                current_time = time.time()
                active_count = sum(1 for uid, l_time in user_last_active.items() if current_time - l_time < 86400)
                wallet_bound = len(user_wallets)
                wallet_unbound = total_users - wallet_bound
                stats_msg = f"📊 **إحصائيات البوت الشاملة (للأدمن):**\n\n👥 إجمالي المستخدمين: `{total_users}`\n🔥 المستخدمين النشطين (آخر 24 ساعة): `{active_count}`\n💳 من ربطوا محفظتهم: `{wallet_bound}`\n⏳ من لم يربطوا محفظتهم: `{wallet_unbound}`\n\n🏆 **أفضل 5 مستخدمين في الإحالات:**\n{top_text}"
            else:
                stats_msg = f"📊 **إحصائيات البوت:**\n\n👥 إجمالي المستخدمين: `{total_users}`\n\n🏆 **أفضل 5 مستخدمين:**\n{top_text}"
            send_main_menu(chat_id, stats_msg)
        elif text == "📞 الدعم الفني":
            send_main_menu(chat_id, f"📞 للتواصل مع الدعم الفني:\n👉 {PRIMARY_ADMIN_USERNAME}")

    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)