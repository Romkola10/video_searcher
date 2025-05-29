import os
import ffmpeg
import requests
import yt_dlp
import yt_dlp
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, ContextTypes
)
logging.basicConfig(level=logging.INFO)

# Змінні оточення для Railway
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Тимчасові папки
TMPDIR = os.getenv("TMPDIR", "/tmp")
VIDEO_FOLDER = os.path.join(TMPDIR, "videos")
CUT_FOLDER = os.path.join(TMPDIR, "cuts")

os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(CUT_FOLDER, exist_ok=True)

# Стани для ConversationHandler
SELECT_VIDEO, WAIT_FOR_TIME = range(2)

# Дані користувача
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Напиши назву фільму 🎥")

async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}&language=uk"
    response = requests.get(url).json()

    if response.get("results"):
        keyboard = []
        for movie in response["results"][:5]:
            title = movie["title"]
            year = movie.get("release_date", "????")[:4]
            movie_id = movie["id"]
            keyboard.append([InlineKeyboardButton(f"{title} ({year})", callback_data=f"movie_{movie_id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Обери варіант:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Нічого не знайшов 😢")

async def movie_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    movie_id = query.data.split("_")[1]

    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=uk&append_to_response=videos"
    movie = requests.get(url).json()

    title = movie["title"]
    overview = movie["overview"]
    poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
    await query.message.reply_photo(poster, caption=f"🎬 {title}\n\n{overview}")

    # Пошук трейлера
    videos = movie.get("videos", {}).get("results", [])
    trailer = next((v for v in videos if v["type"] == "Trailer" and v["site"] == "YouTube"), None)

    if trailer:
        video_url = f"https://www.youtube.com/watch?v={trailer['key']}"
        await query.message.reply_text(f"🔍 Знайдено трейлер: {video_url}")
        logging.info(f"Trailer URL: {video_url}")

        user_id = query.from_user.id
        trailer_path = os.path.join(CUT_FOLDER, f"{user_id}_trailer.mp4")

        ydl_opts = {
            'outtmpl': trailer_path,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': True,
        }

        try:
            await query.message.reply_text("⬇️ Завантажую трейлер...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            await context.bot.send_video(chat_id=query.message.chat_id, video=open(trailer_path, 'rb'))
            await query.message.reply_text("✅ Трейлер завантажено!")
        except Exception as e:
            await query.message.reply_text(f"❌ Помилка завантаження трейлера: {e}")
            logging.error(f"Trailer download error: {e}")
    else:
        await query.message.reply_text("🚫 Трейлер не знайдено 😢")
        logging.info("No trailer found.")

    user_data[query.from_user.id] = {"movie_title": title}
    return SELECT_VIDEO

async def delete_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    video_path = user_data.get(user_id, {}).get("video_path")
    cut_path = user_data.get(user_id, {}).get("cut_path")

    if video_path and os.path.exists(video_path):
        os.remove(video_path)
    if cut_path and os.path.exists(cut_path):
        os.remove(cut_path)

    await update.message.reply_text("Відео та уривок видалено з сервера ✅")
    user_data.pop(user_id, None)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Відмінив.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & (~filters.COMMAND), search_movie)],
        states={},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(movie_selected, pattern="^movie_"))
    app.add_handler(CommandHandler("delete", delete_files))

    app.run_polling()

if __name__ == '__main__':
    main()
