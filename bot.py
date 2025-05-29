import os
import ffmpeg
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackContext, CallbackQueryHandler, ConversationHandler
)

# Змінні оточення для Railway
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Тимчасові папки (Railway чистить /tmp при перезапуску)
TMPDIR = os.getenv("TMPDIR", "/tmp")
VIDEO_FOLDER = os.path.join(TMPDIR, "videos")
CUT_FOLDER = os.path.join(TMPDIR, "cuts")

os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(CUT_FOLDER, exist_ok=True)

# Стани для ConversationHandler
SELECT_VIDEO, WAIT_FOR_TIME = range(2)

# Дані користувача в памʼяті
user_data = {}

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привіт! Напиши назву фільму 🎥")

def search_movie(update: Update, context: CallbackContext):
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
        update.message.reply_text("Обери варіант:", reply_markup=reply_markup)
    else:
        update.message.reply_text("Нічого не знайшов 😢")

def movie_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    movie_id = query.data.split("_")[1]

    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=uk"
    movie = requests.get(url).json()

    title = movie["title"]
    overview = movie["overview"]
    poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

    query.message.reply_photo(poster, caption=f"🎬 {title}\n\n{overview}\n\nНадішли мені відеофайл 🎥")

    user_data[query.from_user.id] = {"movie_title": title}
    return SELECT_VIDEO

def handle_video(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    video_file = update.message.video.get_file()
    video_path = os.path.join(VIDEO_FOLDER, f"{user_id}.mp4")
    video_file.download(video_path)
    user_data[user_id]["video_path"] = video_path

    update.message.reply_text("Вкажи таймкод початку уривку у форматі 00:01:30")
    return WAIT_FOR_TIME

def handle_time(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    start_time = update.message.text
    video_path = user_data[user_id]["video_path"]
    cut_path = os.path.join(CUT_FOLDER, f"{user_id}_cut.mp4")

    try:
        (
            ffmpeg
            .input(video_path, ss=start_time)
            .output(cut_path, t='00:02:00', codec='copy')
            .run(overwrite_output=True)
        )
        context.bot.send_video(chat_id=update.message.chat_id, video=open(cut_path, 'rb'))
        user_data[user_id]["cut_path"] = cut_path
        update.message.reply_text("Готово ✅ Щоб видалити відео з сервера, напиши /delete")
    except Exception as e:
        update.message.reply_text(f"Помилка обрізання: {e}")

    return ConversationHandler.END

def delete_files(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    video_path = user_data.get(user_id, {}).get("video_path")
    cut_path = user_data.get(user_id, {}).get("cut_path")

    if video_path and os.path.exists(video_path):
        os.remove(video_path)
    if cut_path and os.path.exists(cut_path):
        os.remove(cut_path)

    update.message.reply_text("Відео та уривок видалено з сервера ✅")
    user_data.pop(user_id, None)

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Відмінив.")

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
