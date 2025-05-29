import os
import ffmpeg
import requests
import logging
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, ConversationHandler
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

TMPDIR = os.getenv("TMPDIR", "/tmp")
VIDEO_FOLDER = os.path.join(TMPDIR, "videos")
CUT_FOLDER = os.path.join(TMPDIR, "cuts")

os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(CUT_FOLDER, exist_ok=True)

SELECT_VIDEO, WAIT_FOR_TIME = range(2)

user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Напиши назву фільму 🎥")

async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.message.text
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}&language=uk"
        response = requests.get(url).json()

        if response.get("results"):
            keyboard = []
            for movie in response["results"]:
                title = movie["title"]
                year = movie.get("release_date", "????")[:4]
                movie_id = movie["id"]
                keyboard.append([InlineKeyboardButton(f"{title} ({year})", callback_data=f"movie_{movie_id}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Обери варіант:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Нічого не знайшов 😢")
    except Exception as e:
        logger.error(f"Error in search_movie: {e}")
        await update.message.reply_text("Вибач, сталася помилка при пошуку фільму.")

async def movie_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    movie_id = query.data.split("_")[1]

    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=uk"
    movie = requests.get(url).json()

    title = movie["title"]
    overview = movie["overview"]
    poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

    # надсилаємо постер
    query.message.reply_photo(poster)

    # надсилаємо опис
    query.message.reply_text(f"🎬 *{title}*\n\n_{overview}_", parse_mode='Markdown')

    # шукаємо трейлер
    videos_url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language=uk"
    videos = requests.get(videos_url).json()

    youtube_links = []
    for video in videos.get("results", []):
        if video["site"] == "YouTube" and video["type"] in ["Trailer", "Teaser"]:
            youtube_links.append(f"https://www.youtube.com/watch?v={video['key']}")

    if youtube_links:
        trailer_url = youtube_links[0]
        query.message.reply_text("Завантажую трейлер 🎞️...")

        trailer_path = os.path.join(TMPDIR, f"{query.from_user.id}_trailer.mp4")
        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': trailer_path,
            'quiet': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([trailer_url])

            context.bot.send_video(chat_id=query.message.chat_id, video=open(trailer_path, 'rb'), supports_streaming=True)
            os.remove(trailer_path)

        except Exception as e:
            query.message.reply_text(f"Не вдалося завантажити трейлер: {e}")

    else:
        query.message.reply_text("На жаль, трейлеру не знайшло 😢")

    # пропонуємо користувачу відправити своє відео
    query.message.reply_text("Тепер надішли мені відеофайл 🎥, який хочеш обрізати")

    user_data[query.from_user.id] = {"movie_title": title}
    return SELECT_VIDEO

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        video_file = await update.message.video.get_file()
        video_path = os.path.join(VIDEO_FOLDER, f"{user_id}.mp4")
        await video_file.download_to_drive(video_path)
        user_data[user_id]["video_path"] = video_path

        await update.message.reply_text("Вкажи таймкод початку уривку у форматі 00:01:30")
        return WAIT_FOR_TIME
    except Exception as e:
        logger.error(f"Error in handle_video: {e}")
        await update.message.reply_text("Сталася помилка при завантаженні відео. Спробуй ще раз.")

async def handle_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        start_time = update.message.text
        video_path = user_data[user_id]["video_path"]
        cut_path = os.path.join(CUT_FOLDER, f"{user_id}_cut.mp4")

        (
            ffmpeg
            .input(video_path, ss=start_time)
            .output(cut_path, t='00:02:00', codec='copy')
            .run(overwrite_output=True)
        )
        await context.bot.send_video(chat_id=update.message.chat_id, video=open(cut_path, 'rb'))
        user_data[user_id]["cut_path"] = cut_path
        await update.message.reply_text("Готово ✅ Щоб видалити відео з сервера, напиши /delete")
    except Exception as e:
        logger.error(f"Error in handle_time: {e}")
        await update.message.reply_text(f"Помилка обрізання: {e}")

    return ConversationHandler.END

async def delete_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        video_path = user_data.get(user_id, {}).get("video_path")
        cut_path = user_data.get(user_id, {}).get("cut_path")

        if video_path and os.path.exists(video_path):
            os.remove(video_path)
        if cut_path and os.path.exists(cut_path):
            os.remove(cut_path)

        await update.message.reply_text("Відео та уривок видалено з сервера ✅")
        user_data.pop(user_id, None)
    except Exception as e:
        logger.error(f"Error in delete_files: {e}")
        await update.message.reply_text("Помилка при видаленні файлів.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Відмінив.")

print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & (~filters.COMMAND), search_movie)],
        states={
            SELECT_VIDEO: [MessageHandler(filters.VIDEO, handle_video)],
            WAIT_FOR_TIME: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(movie_selected, pattern="^movie_"))
    app.add_handler(CommandHandler("delete", delete_files))

    app.run_polling()

if __name__ == '__main__':
    main()
