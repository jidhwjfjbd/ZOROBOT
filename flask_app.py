import os
import time
import hashlib
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# تم تعيين البيانات الخاصة بك مباشرة هنا
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "7963385287:AAH0pWb-Yn70WbWqGjE90P7O0h57W82K6Zc") # استبدله بالتوكن الفعلي إذا لزم الأمر
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
BOT_USERNAME = "freemoneytgffbot"
ADMIN_IDS = [8667934765, 8557464787]
PRIMARY_ADMIN_USERNAME = "@Admin"
PROOF_CHANNEL_ID = os.environ.get("PROOF_CHANNEL_ID", "-100xxxxxxx")

# قواعد البيانات في الذاكرة
all_bot_users = set()
user_balances = {}
user_wallets = {}
user_referrals = {}
invited_by = {}
verified_users = set()
user_has_pending = set()
pending_withdrawals = {}
user_states = {}
admin_states = {}
broadcast_data = {}
temp_bot_data = {}
user_last_active = {}
user_task_progress = {}

# نظام لغات المستخدمين (الافتراضي: العربية ar)
user_languages = {}

# القواميس للغتين (العربية والإنجليزية)
LANGS = {
    "ar": {
        "menu_ref": "🎁 رابط الإحالة",
        "menu_balance": "💎 رصيدي والسحب",
        "menu_wallet": "💳 ربط المحفظة",
        "menu_stats": "📊 إحصائيات البوت",
        "menu_support": "📞 الدعم الفني",
        "menu_lang": "🌐 Language: English",
        "back_btn": "🔙 العودة للقائمة الرئيسية",
        "check_sub": "✅ تحقق من الاشتراك",
        "click_target": "👉 اضغط هنا للتنفيذ (تكرار {current}/{target})",
        "next_task": "⏭ الانتقال للمهمة التالية",
        "welcome": "أهلاً بك مجدداً 👋",
        "lang_switched": "✅ تم تغيير اللغة إلى العربية بنجاح."
    },
    "en": {
        "menu_ref": "🎁 Referral Link",
        "menu_balance": "💎 Balance & Withdraw",
        "menu_wallet": "💳 Bind Wallet",
        "menu_stats": "📊 Bot Statistics",
        "menu_support": "📞 Support",
        "menu_lang": "🌐 اللغة: العربية",
        "back_btn": "🔙 Back to Main Menu",
        "check_sub": "✅ Check Subscription",
        "click_target": "👉 Click here ({current}/{target})",
        "next_task": "⏭ Next Task",
        "welcome": "Welcome back 👋",
        "lang_switched": "✅ Language changed to English successfully."
    }
}

def get_lang(chat_id):
    return user_languages.get(chat_id, "ar")

def t(chat_id, key):
    lang = get_lang(chat_id)
    return LANGS.get(lang, LANGS["ar"]).get(key, key)

bot_settings = {
    "referral_reward": 0.1,
    "min_withdrawal": 0.5
}

forced_channels = []
forced_bots = []
withdrawal_counter = 0

def check_channel_membership(chat_id, channel_username):
    try:
        url = f"{TELEGRAM_API_URL}/getChatMember?chat_id={channel_username}&user_id={chat_id}"
        res = requests.get(url).json()
        if res.get("ok"):
            status = res["result"].get("status")
            return status in ["member", "administrator", "creator"]
    except Exception:
        pass
    return False

def get_next_pending_task(chat_id):
    if chat_id in ADMIN_IDS or chat_id in verified_users:
        return "done", None

    progress = user_task_progress.setdefault(chat_id, {"channels_done": False, "bot_idx": 0, "bot_repeat_count": 0, "bot_clicks": {}})
    
    if not progress["channels_done"]:
        for ch in forced_channels:
            if not check_channel_membership(chat_id, ch):
                return "channel", ch
        progress["channels_done"] = True

    b_idx = progress["bot_idx"]
    if b_idx < len(forced_bots):
        return "bot", b_idx

    verified_users.add(chat_id)
    if chat_id in invited_by:
        ref_id = invited_by[chat_id]
        if ref_id not in user_referrals.setdefault(ref_id, []):
            user_referrals[ref_id].append(chat_id)
            reward = bot_settings["referral_reward"]
            user_balances[ref_id] = user_balances.get(ref_id, 0.0) + reward
            try:
                ref_lang = get_lang(ref_id)
                msg_text = f"🎉 مبروك! انضم شخص عبر رابط إحالتك وتم التحقق بنجاح. حصلت على `{reward} TON`." if ref_lang == "ar" else f"🎉 Congrats! A new user joined via your referral link and verified successfully. You earned `{reward} TON`."
                requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": ref_id, "text": msg_text, "parse_mode": "Markdown"})
            except Exception:
                pass
    return "done", None

def send_next_task_prompt(chat_id):
    task_type, target = get_next_pending_task(chat_id)
    lang = get_lang(chat_id)
    
    if task_type == "done":
        send_main_menu(chat_id, "🎉 تم الانتهاء من جميع المهام بنجاح!" if lang == "ar" else "🎉 All tasks completed successfully!")
        return
    
    if task_type == "channel":
        channels_text = "\n".join([f"📢 [الانضمام إلى {ch}](https://t.me/{ch.replace('@','')})" for ch in forced_channels])
        text = f"⚠️ **الخطوة الأولى:** يجب عليك الانضمام إلى القنوات التالية أولاً للاستمرار:\n\n{channels_text}" if lang == "ar" else f"⚠️ **Step 1:** You must join the following channels first to continue:\n\n{channels_text}"
        markup = {"inline_keyboard": [[{"text": t(chat_id, "check_sub"), "callback_data": "check_next_task"}]]}
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": markup, "disable_web_page_preview": True})
    
    elif task_type == "bot":
        b_data = forced_bots[target]
        b_name = b_data["name"]
        b_url = b_data["url"]
        target_repeats = b_data.get("repeat_target", 3)
        progress = user_task_progress.get(chat_id, {})
        current_repeats = progress.get("bot_repeat_count", 0)
        
        btn_text = f"👉 اضغط هنا ({current_repeats}/{target_repeats})" if lang == "ar" else f"👉 Click here ({current_repeats}/{target_repeats})"
        text = f"🤖 **مهمة تفاعلية:** يرجى التفاعل مع البوت/الموقع التالي (`{b_name}`) عدة مرات:" if lang == "ar" else f"🤖 **Interactive Task:** Please interact with the following bot/site (`{b_name}`) multiple times:"
        
        markup = {"inline_keyboard": [
            [{"text": f"🔗 {b_name}", "url": b_url}],
            [{"text": btn_text, "callback_data": f"click_bot_{target}"}]
        ]}
        requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": markup})
def execute_broadcast(admin_id):
    b_msg = broadcast_data.get(admin_id)
    if not b_msg: 
        return
    success = 0
    for uid in list(all_bot_users):
        try:
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
            [{"text": t(chat_id, "menu_ref")}, {"text": t(chat_id, "menu_balance")}],
            [{"text": t(chat_id, "menu_wallet")}, {"text": t(chat_id, "menu_stats")}],
            [{"text": t(chat_id, "menu_support")}, {"text": t(chat_id, "menu_lang")}]
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

    # تجاهل تام لأي رسائل أو تفاعلات قادمة من المجموعات والقروبات العامة
    if "message" in update:
        chat_type = update["message"]["chat"].get("type", "private")
        if chat_type in ["group", "supergroup"]:
            return "OK", 200

    if "callback_query" in update:
        cb = update["callback_query"]
        chat_type = cb["message"]["chat"].get("type", "private")
        if chat_type in ["group", "supergroup"]:
            try:
                requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"]})
            except Exception:
                pass
            return "OK", 200

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
                send_telegram_message(chat_id, "📢 أرسل الآن المنشور المراد إذاعته (صورة، نص، فيديو، أو ملف):")
            elif data == "set_ref_reward": 
                admin_states[chat_id] = "waiting_ref_reward"
                send_telegram_message(chat_id, "✍ أدخل سعر الإحالة الجديد:")
            elif data == "set_min_withdrawal": 
                admin_states[chat_id] = "waiting_min_withdrawal"
                send_telegram_message(chat_id, "✍️ أدخل الحد الأدنى للسحب الجديد:")
            elif data == "add_channel": 
                admin_states[chat_id] = "waiting_add_channel"
                send_telegram_message(chat_id, "📢 أرسل معرف القناة أو المجموعة (مثال: `@ChannelUsername`):")
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
                send_telegram_message(chat_id, "🤖 أرسل رابط البوت أو الميني أب (Mini App):")
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

        back_text_ar = LANGS["ar"]["back_btn"]
        back_text_en = LANGS["en"]["back_btn"]
        if text in [back_text_ar, back_text_en]:
            user_states.pop(chat_id, None)
            admin_states.pop(chat_id, None)
            task_type, _ = get_next_pending_task(chat_id)
            if task_type != "done":
                send_next_task_prompt(chat_id)
            else:
                send_main_menu(chat_id, back_text_ar if get_lang(chat_id) == "ar" else back_text_en)
            return "OK", 200

        if text in ["🌐 Language: English", "🌐 اللغة: العربية"]:
            current_lang = get_lang(chat_id)
            new_lang = "en" if current_lang == "ar" else "ar"
            user_languages[chat_id] = new_lang
            send_main_menu(chat_id, t(chat_id, "lang_switched"))
            return "OK", 200

        if chat_id in ADMIN_IDS and chat_id in admin_states:
            state = admin_states[chat_id]
            if state == "waiting_broadcast":
                admin_states.pop(chat_id, None)
                broadcast_data[chat_id] = msg["message_id"]
                requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                    "chat_id": chat_id, 
                    "text": "📌 معاينة الرسالة بالأعلى.\nهل تريد تأكيد إرسالها لجميع المستخدمين؟",
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
                send_telegram_message(chat_id, f"✅ تم إضافة القناة/المجموعة `{ch}` بنجاح للاشتراك الإجباري.")
            elif state == "waiting_bot_url":
                temp_bot_data[chat_id] = {"url": text.strip()}
                admin_states[chat_id] = "waiting_bot_name"
                send_telegram_message(chat_id, "✍️ أرسل الاسم الذي سيظهر للمستخدم كمميز في قائمة البوتات:")
            elif state == "waiting_bot_name":
                admin_states.pop(chat_id, None)
                b_url = temp_bot_data.pop(chat_id, {}).get("url", "")
                b_name = text.strip()
                forced_bots.append({"name": b_name, "url": b_url, "repeat_target": 3})
                user_task_progress.clear()
                send_telegram_message(chat_id, f"✅ تم إضافة البوت `{b_name}` بنجاح.")
            return "OK", 200

        if chat_id in user_states:
            state = user_states.pop(chat_id, None)
            lang = get_lang(chat_id)
            if state == "waiting_wallet":
                user_wallets[chat_id] = text.strip()
                send_main_menu(chat_id, f"✅ تم حفظ محفظة TON:\n`{text.strip()}`" if lang == "ar" else f"✅ TON wallet saved:\n`{text.strip()}`")
            elif state == "waiting_withdrawal_amount":
                if chat_id in user_has_pending:
                    send_main_menu(chat_id, "⚠ لديك طلب سحب قيد المراجعة بالفعل." if lang == "ar" else "⚠ You already have a pending withdrawal request.")
                else:
                    try:
                        amount = float(text.strip())
                        bal = 999999.0 if chat_id in ADMIN_IDS else user_balances.get(chat_id, 0.0)
                        if amount < bot_settings["min_withdrawal"] or amount > bal:
                            err_msg = f"❌ المبلغ غير صالح أو أقل من الحد الأدنى (`{bot_settings['min_withdrawal']} TON`) أو رصيدك لا يكفي." if lang == "ar" else f"❌ Invalid amount, below minimum (`{bot_settings['min_withdrawal']} TON`), or insufficient balance."
                            send_main_menu(chat_id, err_msg)
                        else:
                            wallet = user_wallets.get(chat_id)
                            if not wallet: 
                                send_main_menu(chat_id, "⚠️ يجب ربط محفظة TON أولاً!" if lang == "ar" else "⚠️ You must bind a TON wallet first!")
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
                                success_w_msg = f"🎉 تم تقديم طلب السحب بنجاح بقيمة `{amount} TON` وهو قيد المراجعة." if lang == "ar" else f"🎉 Withdrawal request submitted successfully for `{amount} TON` and is under review."
                                send_main_menu(chat_id, success_w_msg)
                    except ValueError: 
                        send_main_menu(chat_id, "❌ قيمة غير صالحة." if lang == "ar" else "❌ Invalid value.")
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
                send_main_menu(chat_id, t(chat_id, "welcome"))
            else:
                send_next_task_prompt(chat_id)
            return "OK", 200

        if chat_id not in ADMIN_IDS:
            task_type, _ = get_next_pending_task(chat_id)
            if task_type != "done": 
                send_next_task_prompt(chat_id)
                return "OK", 200

        lang = get_lang(chat_id)
        ref_text_key = t(chat_id, "menu_ref")
        bal_text_key = t(chat_id, "menu_balance")
        wallet_text_key = t(chat_id, "menu_wallet")
        stats_text_key = t(chat_id, "menu_stats")
        support_text_key = t(chat_id, "menu_support")

        if text == ref_text_key:
            reward_val = bot_settings["referral_reward"]
            refs_count = len(user_referrals.get(chat_id, []))
            if lang == "ar":
                msg = f"🎁 رابط الإحالة الخاص بك:\n`https://t.me/{BOT_USERNAME}?start={chat_id}`\n\n💰 **سعر الإحالة:** `{reward_val} TON` لكل شخص يقوم بالانضمام وتخطّي المهام والتحقق الكامل.\nعدد إحالاتك الناجحة: `{refs_count}`"
            else:
                msg = f"🎁 Your referral link:\n`https://t.me/{BOT_USERNAME}?start={chat_id}`\n\n💰 **Referral Reward:** `{reward_val} TON` per verified referral.\nSuccessful referrals: `{refs_count}`"
            send_main_menu(chat_id, msg)
            
        elif text == bal_text_key:
            bal = 999999.0 if chat_id in ADMIN_IDS else user_balances.get(chat_id, 0.0)
            min_w = bot_settings["min_withdrawal"]
            user_states[chat_id] = "waiting_withdrawal_amount"
            back_btn_txt = LANGS[lang]["back_btn"]
            if lang == "ar":
                msg = f"💎 رصيدك الحالي: `{bal:.2f} TON`\n⚠️ **الحد الأدنى للسحب هو:** `{min_w} TON`\n\n✍️ أدخل المبلغ المراد سحبه الآن:"
            else:
                msg = f"💎 Current Balance: `{bal:.2f} TON`\n⚠️ **Minimum Withdrawal:** `{min_w} TON`\n\n✍️ Enter amount to withdraw:"
            send_telegram_message(chat_id, msg, reply_markup={"keyboard": [[{"text": back_btn_txt}]], "resize_keyboard": True})
            
        elif text == wallet_text_key:
            user_states[chat_id] = "waiting_wallet"
            back_btn_txt = LANGS[lang]["back_btn"]
            msg = "💳 أرسل عنوان محفظة TON الخاصة بك:" if lang == "ar" else "💳 Send your TON wallet address:"
            send_telegram_message(chat_id, msg, reply_markup={"keyboard": [[{"text": back_btn_txt}]], "resize_keyboard": True})
            
        elif text == stats_text_key:
            total_users = len(all_bot_users)
            sorted_refs = sorted(user_referrals.items(), key=lambda x: len(x[1]), reverse=True)[:5]
            top_text = ""
            for idx, (uid, refs) in enumerate(sorted_refs, 1):
                top_text += f"{idx}. UID: (`{uid}`) - Refs: `{len(refs)}`\n"
            if not top_text:
                top_text = "لا توجد إحالات مسجلة بعد." if lang == "ar" else "No referrals recorded yet."

            if chat_id in ADMIN_IDS:
                current_time = time.time()
                active_count = sum(1 for uid, l_time in user_last_active.items() if current_time - l_time < 86400)
                wallet_bound = len(user_wallets)
                wallet_unbound = total_users - wallet_bound
                if lang == "ar":
                    stats_msg = f"📊 **إحصائيات البوت الشاملة (للأدمن):**\n\n👥 إجمالي المستخدمين: `{total_users}`\n🔥 النشطين (24 ساعة): `{active_count}`\n💳 من ربطوا محفظتهم: `{wallet_bound}`\n⏳ من لم يربطوا: `{wallet_unbound}`\n\n🏆 **أفضل الإحالات:**\n{top_text}"
                else:
                    stats_msg = f"📊 **Admin Bot Stats:**\n\n👥 Total Users: `{total_users}`\n🔥 Active (24h): `{active_count}`\n💳 Wallets Bound: `{wallet_bound}`\n⏳ Unbound: `{wallet_unbound}`\n\n🏆 **Top Referrers:**\n{top_text}"
            else:
                if lang == "ar":
                    stats_msg = f"📊 **إحصائيات البوت:**\n\n👥 إجمالي المستخدمين: `{total_users}`\n\n🏆 **أفضل المستخدمين:**\n{top_text}"
                else:
                    stats_msg = f"📊 **Bot Statistics:**\n\n👥 Total Users: `{total_users}`\n\n🏆 **Top Users:**\n{top_text}"
            send_main_menu(chat_id, stats_msg)
            
        elif text == support_text_key:
            if lang == "ar":
                support_msg = f"📞 للتواصل مع الدعم الفني:\n👉 {PRIMARY_ADMIN_USERNAME}"
            else:
                support_msg = f"📞 Contact Support:\n👉 {PRIMARY_ADMIN_USERNAME}"
            send_main_menu(chat_id, support_msg)

    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)