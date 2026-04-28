import os, re, uuid, logging, shutil, glob
from flask import Flask, request, Response
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
user_settings = {}

@app.route("/ping")
def ping():
    return Response("OK", status=200)

@app.route("/health")
def health():
    return Response("OK", status=200)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ""
    return Response("Bad Request", status=403)

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Hello! YouTube Downloader Bot!\n\nSend YouTube link\n/settings change format")

@bot.message_handler(commands=["settings"])
def settings(message):
    uid = message.from_user.id
    if uid not in user_settings:
        user_settings[uid] = {"format": "video"}
    kb = InlineKeyboardMarkup()
    f = "Video" if user_settings[uid]["format"] == "video" else "Audio"
    kb.add(InlineKeyboardButton(f"Format: {f}", callback_data="tg"))
    bot.reply_to(message, "Settings:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "tg")
def toggle(call):
    uid = call.from_user.id
    if uid not in user_settings:
        user_settings[uid] = {"format": "video"}
    user_settings[uid]["format"] = "audio" if user_settings[uid]["format"] == "video" else "video"
    bot.answer_callback_query(call.id, "Changed!")
    kb = InlineKeyboardMarkup()
    f = "Video" if user_settings[uid]["format"] == "video" else "Audio"
    kb.add(InlineKeyboardButton(f"Format: {f}", callback_data="tg"))
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.message_handler(func=lambda m: True)
def dl(message):
    u = re.search(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+", message.text)
    if not u:
        bot.reply_to(message, "Send YouTube link!")
        return
    url = u.group(0)
    uid = message.from_user.id
    if uid not in user_settings:
        user_settings[uid] = {"format": "video"}
    fmt = user_settings[uid]["format"]
    msg = bot.reply_to(message, "Downloading...")
    folder = f"/tmp/d_{uuid.uuid4().hex[:6]}"
    os.makedirs(folder, exist_ok=True)
    
    # এখানে কুকিজ অপশন যুক্ত করা হয়েছে
    opts = {"outtmpl": f"{folder}/%(title).50s.%(ext)s", "quiet": True, "max_downloads": 1, "cookiefile": "cookies.txt"}
    
    if fmt == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = "best[ext=mp4]/best"
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        files = glob.glob(f"{folder}/*")
        if not files:
            bot.edit_message_text("No file!", message.chat.id, msg.message_id)
            return
        for f in files:
            sz = os.path.getsize(f)
            if sz > 48_000_000: # 48MB লিমিট
                bot.edit_message_text("File > 48MB!", message.chat.id, msg.message_id)
                continue
            with open(f, "rb") as file:
                if f.endswith(".mp3"):
                    bot.send_audio(message.chat.id, file)
                else:
                    bot.send_video(message.chat.id, file)
            bot.edit_message_text("Done!", message.chat.id, msg.message_id)
        shutil.rmtree(folder, ignore_errors=True)
    except Exception as e:
        bot.edit_message_text(f"Error: {str(e)[:100]}", message.chat.id, msg.message_id)
        shutil.rmtree(folder, ignore_errors=True)

# Webhook Setup
try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
except Exception as e:
    print(f"Webhook setup failed: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
