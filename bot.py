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

user_data = {}

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
    bot.reply_to(message, "Hello! YouTube Downloader Bot!\n\nযেকোনো ইউটিউব লিংক দিন, আমি এভেইলেবল ফরম্যাটগুলোর লিস্ট দেখাবো।")

@bot.message_handler(func=lambda m: True)
def fetch_formats(message):
    u = re.search(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+", message.text)
    if not u:
        bot.reply_to(message, "Please send a valid YouTube link!")
        return
    
    url = u.group(0)
    uid = message.from_user.id
    user_data[uid] = {"url": url} 
    
    msg = bot.reply_to(message, "🔍 Checking available formats...")
    
    # এখানে 'format': 'b' যুক্ত করা হয়েছে যাতে সে চেকিংয়ের সময় এরর না দেয়
    opts = {'cookiefile': 'cookies.txt', 'quiet': True, 'format': 'b'}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        formats = info.get('formats', [])
        kb = InlineKeyboardMarkup(row_width=1)
        
        added_res = set()
        
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                res = f.get('height', 0)
                if res and res not in added_res:
                    size_bytes = f.get('filesize') or f.get('filesize_approx') or 0
                    size_mb = size_bytes / (1024 * 1024)
                    
                    if size_mb > 0 and size_mb < 48:
                        added_res.add(res)
                        btn_text = f"🎬 {res}p Video - {size_mb:.1f} MB"
                        kb.add(InlineKeyboardButton(btn_text, callback_data=f"dl_{f['format_id']}"))

        for f in formats:
            if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('ext') == 'm4a':
                size_bytes = f.get('filesize') or f.get('filesize_approx') or 0
                size_mb = size_bytes / (1024 * 1024)
                if size_mb < 48:
                    btn_text = "🎵 Audio (m4a)"
                    if size_mb > 0: btn_text += f" - {size_mb:.1f} MB"
                    kb.add(InlineKeyboardButton(btn_text, callback_data=f"dl_{f['format_id']}"))
                    break 
        
        if len(kb.keyboard) == 0:
            bot.edit_message_text("Sorry, no suitable format found under 48MB.", message.chat.id, msg.message_id)
        else:
            bot.edit_message_text("👇 Select a format to download:", message.chat.id, msg.message_id, reply_markup=kb)
            
    except Exception as e:
        bot.edit_message_text(f"Error fetching formats: {str(e)[:100]}", message.chat.id, msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dl_"))
def download_selected_format(call):
    uid = call.from_user.id
    if uid not in user_data:
        bot.answer_callback_query(call.id, "Session expired. Please send the link again.")
        return
    
    url = user_data[uid]["url"]
    format_id = call.data.split("_")[1] 
    
    bot.edit_message_text("⏳ Downloading... Please wait.", call.message.chat.id, call.message.message_id)
    
    folder = f"/tmp/d_{uuid.uuid4().hex[:6]}"
    os.makedirs(folder, exist_ok=True)
    
    opts = {
        "format": format_id,
        "outtmpl": f"{folder}/%(title).50s.%(ext)s",
        "quiet": True,
        "cookiefile": "cookies.txt",
        "max_downloads": 1
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
            
        files = glob.glob(f"{folder}/*")
        if not files:
            bot.edit_message_text("Download failed, no file found!", call.message.chat.id, call.message.message_id)
            return
            
        for f in files:
            with open(f, "rb") as file:
                if f.endswith(".m4a") or f.endswith(".mp3"):
                    bot.send_audio(call.message.chat.id, file)
                else:
                    bot.send_video(call.message.chat.id, file)
                    
        bot.edit_message_text("✅ Done!", call.message.chat.id, call.message.message_id)
        shutil.rmtree(folder, ignore_errors=True)
        
    except Exception as e:
        bot.edit_message_text(f"Error: {str(e)[:100]}", call.message.chat.id, call.message.message_id)
        shutil.rmtree(folder, ignore_errors=True)

# Webhook Setup
try:
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
except Exception as e:
    print(f"Webhook setup failed: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
