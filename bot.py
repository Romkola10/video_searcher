import os
import ffmpeg
import requests
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, ContextTypes
)

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

    # Знаходимо трейлер
    trailers = movie.get("videos", {}).get("results", [])
    youtube_key = None
    for v in trailers:
        if v["type"] == "Trailer" and v["site"] == "YouTube":
            youtube_key = v["key"]
            break

    if youtube_key:
        await query.message.reply_text("Завантажую трейлер 🎞️ ...")
        video_url = f"https://www.youtube.com/watch?v={youtube_key}"
        trailer_path = os.path.join(VIDEO_FOLDER, f"{query.from_user.id}_trailer.mp4")

        ydl_opts = {
            'outtmpl': trailer_path,
            'format': 'best[ext=mp4]',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        await query.message.reply_video(video=open(trailer_path, 'rb'))
        os.remove(trailer_path)
    else:
        await query.message.reply_text("На жаль, трейлер не знайдено 😢")

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
