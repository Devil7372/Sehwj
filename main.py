
import os
import json
import cv2
import numpy as np
import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from config import TELEGRAM_BOT_TOKEN, ADMIN_ID, LOG_CHANNEL_ID, UPDATE_CHANNEL, DISCUSSION_GROUP
import face_recognition
from datetime import datetime

# Storage files
USER_DB_FILE = "users.json"
user_images = {}

# Helper: Load user database
def load_user_db():
    if not os.path.exists(USER_DB_FILE):
        return {}
    with open(USER_DB_FILE, "r") as f:
        return json.load(f)

# Helper: Save user database
def save_user_db(data):
    with open(USER_DB_FILE, "w") as f:
        json.dump(data, f)

# Helper: Check and update daily limit
def can_user_use(user_id):
    db = load_user_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if str(user_id) not in db:
        db[str(user_id)] = {"count": 0, "date": today}
    if db[str(user_id)]["date"] != today:
        db[str(user_id)] = {"count": 0, "date": today}

    if db[str(user_id)]["count"] >= 5:
        return False
    db[str(user_id)]["count"] += 1
    save_user_db(db)
    return True

# Swap faces using face_recognition
def swap_faces(img1, img2):
    face_locations1 = face_recognition.face_locations(img1)
    face_locations2 = face_recognition.face_locations(img2)

    if not face_locations1 or not face_locations2:
        return None

    top1, right1, bottom1, left1 = face_locations1[0]
    top2, right2, bottom2, left2 = face_locations2[0]

    face1 = img1[top1:bottom1, left1:right1]
    face2 = img2[top2:bottom2, left2:right2]

    face1 = cv2.resize(face1, (right2 - left2, bottom2 - top2))
    img2[top2:bottom2, left2:right2] = face1

    return img2

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    # Log new user
    await context.bot.send_message(
        chat_id=LOG_CHANNEL_ID,
        text=f"👤 New user: {user_name} (ID: {user_id})"
    )

    buttons = [
        [InlineKeyboardButton("📢 Updates", url=UPDATE_CHANNEL)],
        [InlineKeyboardButton("💬 Discussion", url=DISCUSSION_GROUP)]
    ]
    await update.message.reply_text(
        "👋 Welcome to Face Swap Bot!

"
        "Send me *2 clear face photos*, and I’ll swap them!

"
        "Type /guide to learn how to use.",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

# User guide
async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *User Guide*:

"
        "1. Send 2 photos (one after another).
"
        "2. Faces will be detected and swapped.
"
        "3. Limit: 5 swaps per day.

"
        "⚠️ Make sure faces are clearly visible!",
        parse_mode="Markdown"
    )

# Broadcast
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = update.message.text.replace("/broadcast", "").strip()
    if not msg:
        await update.message.reply_text("❌ Empty broadcast message.")
        return

    db = load_user_db()
    count = 0
    for uid in db:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
            count += 1
        except:
            continue
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")

# Stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    db = load_user_db()
    total_users = len(db)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    active_today = sum(1 for u in db.values() if u['date'] == today)
    await update.message.reply_text(
        f"📊 *Bot Stats:*

"
        f"👥 Total users: {total_users}
"
        f"📅 Active today: {active_today}",
        parse_mode="Markdown"
    )

# Handle photo uploads
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not can_user_use(user_id):
        await update.message.reply_text("🚫 You’ve reached your *daily limit* of 5 swaps.", parse_mode="Markdown")
        return

    photo_file = await update.message.photo[-1].get_file()
    file_path = f"{user_id}_{len(user_images.get(user_id, []))}.jpg"
    await photo_file.download_to_drive(file_path)

    user_images.setdefault(user_id, []).append(file_path)

    if len(user_images[user_id]) == 2:
        img1 = face_recognition.load_image_file(user_images[user_id][0])
        img2 = face_recognition.load_image_file(user_images[user_id][1])

        result = swap_faces(img1, img2)

        if result is not None:
            result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
            output_path = f"{user_id}_swapped.jpg"
            cv2.imwrite(output_path, result_bgr)
            with open(output_path, 'rb') as f:
                await update.message.reply_photo(f, caption="✅ Face swapped!")
            os.remove(output_path)
        else:
            await update.message.reply_text("😔 Couldn't detect faces in both images.")

        for path in user_images[user_id]:
            os.remove(path)
        user_images[user_id] = []
    else:
        await update.message.reply_text("📸 Send another photo to proceed with the face swap.")

# Main bot
async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("guide", guide))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
