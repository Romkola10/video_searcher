import os
import requests
import subprocess
import yt_dlp
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, ContextTypes
)

logging.basicConfig(level=logging.INFO)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

TMPDIR = os.getenv("TMPDIR", "/tmp")

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

#     if not trailer_url:
#         await query.message.reply_text("Трейлер не знайдено 😢")
#         return

#     trailer_path = os.path.join(TMPDIR, f"{movie_id}_trailer.mp4")

#     ydl_opts = {
#         'format': 'best',          # Просто найкращий формат (без міксування)
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

    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=uk&append_to_response=videos"
    movie = requests.get(url).json()

    title = movie["title"]
    overview = movie["overview"]
    poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

    await query.message.reply_photo(poster, caption=f"🎬 {title}\n\n{overview}")

    videos = movie.get("videos", {}).get("results", [])
    trailer_url = None
    for video in videos:
        if video["type"] == "Trailer" and video["site"] == "YouTube":
            trailer_url = f"https://www.youtube.com/watch?v={video['key']}"
            break

    if not trailer_url:
        await query.message.reply_text("Трейлер не знайдено 😢")
        return

     # Логування шляху до ffmpeg
    ffmpeg_path = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True).stdout.strip()
    logging.info(f"ffmpeg path: {ffmpeg_path}")

    if not ffmpeg_path:
        await query.message.reply_text("FFmpeg не знайдено на сервері, трейлер не завантажується.")
        return

    trailer_path = os.path.join(TMPDIR, f"{movie_id}_trailer.mp4")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': trailer_path,
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': ffmpeg_path,  # явно вказати шлях до ffmpeg
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([trailer_url])
    except Exception as e:
        await query.message.reply_text(f"Помилка завантаження трейлера: {e}")
        return

    with open(trailer_path, 'rb') as video_file:
        await query.message.reply_video(video=video_file, supports_streaming=True)


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

    app.run_polling()

if __name__ == '__main__':
    main()
