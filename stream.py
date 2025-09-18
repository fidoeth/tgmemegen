import base64
from dotenv import load_dotenv
import os, logging, tempfile
from telegram import Update, BotCommand, InputMediaPhoto
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, ApplicationBuilder, ContextTypes
from telegram.request import HTTPXRequest
from openai import OpenAI

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

client = OpenAI(api_key=OPENAI_API_KEY)

async def floppify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg    = update.message
    target = msg.reply_to_message
    if not target:
        return await msg.reply_text("❗️ Reply to an image with /floppify to use this command.")

    # 1) Grab the Telegram File object
    if target.photo:
        tg_file = await target.photo[-1].get_file()
    elif target.document:
        doc = target.document
        if doc.mime_type and doc.mime_type.startswith("image/") or \
           doc.file_name.lower().endswith(IMAGE_EXTENSIONS):
            tg_file = await doc.get_file()
        else:
            return await msg.reply_text("❗️ That file isn’t an image. Send a PNG/JPG and reply /floppify.")
    else:
        return await msg.reply_text("❗️ Reply to a photo or image-file with /floppify.")

    # 2) Download to a temp file (preserve extension so mime is correct)
    ext = os.path.splitext(tg_file.file_path or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        await tg_file.download_to_drive(tmp.name)
        in_path = tmp.name

    # 3) Build prompt
    DEFAULT_PROMPT = (
        "Replace the main subject of this image with a photorealistic caracal cat "
        "in the same lighting and style, seamlessly integrated."
    )
    user_ctx = " ".join(context.args)
    prompt = f"{DEFAULT_PROMPT} {user_ctx}" if user_ctx else DEFAULT_PROMPT

    # 4) Call images.edit exactly like the example
    await context.bot.send_chat_action(msg.chat.id, ChatAction.UPLOAD_PHOTO)
    with open(in_path, "rb") as img_file:
        stream = client.images.edit(
            model="gpt-image-1",
            image=[img_file],
            prompt=prompt,
            stream=True,
            partial_images=2
        )
    preview_msg = None
    for event in stream:
        await context.bot.send_chat_action(msg.chat.id, ChatAction.UPLOAD_PHOTO)
        
        img_bytes = base64.b64decode(event.b64_json)
        media = InputMediaPhoto(img_bytes)

        if preview_msg:
            await preview_msg.edit_media(media)
        else:
            preview_msg = await msg.reply_photo(img_bytes)

async def on_startup(app):
    await app.bot.set_my_commands([
        BotCommand("floppify", "Floppify an image by replying to it with this command.")
    ])

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception in handler:", exc_info=context.error)
    if update and getattr(update, "message", None):
        await update.message.reply_text("⚠️ Oops, something went wrong. Try again later.")

def main():
    httpx_req = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=10.0,
        media_write_timeout=60.0,
    )

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .request(httpx_req)
        .post_init(on_startup)
        .build()
    )

    app.add_handler(CommandHandler("floppify", floppify))
    app.add_error_handler(error_handler)

    print("🤖 Bot is running…")
    app.run_polling()

if __name__ == "__main__":
    main()
