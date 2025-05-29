import os
import requests
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

# async def movie_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     await query.answer()
#     movie_id = query.data.split("_")[1]

#     url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=uk&append_to_response=videos"
#     movie = requests.get(url).json()

#     title = movie["title"]
#     overview = movie["overview"]
#     poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

#     await query.message.reply_photo(poster, caption=f"🎬 {title}\n\n{overview}")

#     videos = movie.get("videos", {}).get("results", [])
#     trailer_url = None
#     for video in videos:
#         if video["type"] == "Trailer" and video["site"] == "YouTube":
#             trailer_url = f"https://www.youtube.com/watch?v={video['key']}"
#             break

#     if trailer_url is None:
#         await query.message.reply_text("Трейлер не знайдено 😢")
#         return

#     trailer_path = os.path.join(TMPDIR, f"{movie_id}_trailer.mp4")

#     ydl_opts = {
#         'format': 'best[ext=mp4]/best',
#         'outtmpl': trailer_path,
#         'quiet': True,
#         'no_warnings': True,
#     }

#     try:
#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             ydl.download([trailer_url])
#     except Exception as e:
#         await query.message.reply_text(f"Помилка завантаження трейлера: {e}")
#         return

#     with open(trailer_path, 'rb') as video_file:
#         await query.message.reply_video(video=video_file, supports_streaming=True)

async def movie_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    movie_id = query.data.split("_")[1]

    # Завантажуємо деталі фільму з відео
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=uk&append_to_response=videos"
    movie = requests.get(url).json()

    title = movie["title"]
    overview = movie["overview"]
    poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

    # Надсилаємо постер і опис
    await query.message.reply_photo(poster, caption=f"🎬 {title}\n\n{overview}")

    videos = movie.get("videos", {}).get("results", [])
    trailer_url = None

    # Шукаємо трейлер
    for video in videos:
        if video["type"] == "Trailer" and video["site"] == "YouTube":
            trailer_url = f"https://www.youtube.com/watch?v={video['key']}"
            break

    # Якщо трейлер є — качаємо і надсилаємо
    if trailer_url:
        await query.message.reply_text("🎞️ Завантажую трейлер...")
        trailer_path = os.path.join(TMPDIR, f"{movie_id}_trailer.mp4")

        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': trailer_path,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([trailer_url])

            with open(trailer_path, 'rb') as video_file:
                await query.message.reply_video(video=video_file, supports_streaming=True)

        except Exception as e:
            await query.message.reply_text(f"Помилка завантаження трейлера: {e}")

    else:
        await query.message.reply_text("Трейлер не знайдено 😢")

    # Шукаємо інші відео з YouTube (макс 3)
    yt_videos = []
    for video in videos:
        if video["site"] == "YouTube":
            yt_videos.append(f"📺 {video['type']}: https://www.youtube.com/watch?v={video['key']}")
            if len(yt_videos) == 3:
                break

    if yt_videos:
        await query.message.reply_text("🎬 Додаткові відео по фільму:")
        for vid in yt_videos:
            await query.message.reply_text(vid)
    else:
        await query.message.reply_text("Жодних додаткових відео по цьому фільму не знайдено 😢")



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
