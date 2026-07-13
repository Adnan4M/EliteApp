"""Diagnostic: show everything @MedHelpRobot_bot has ever sent us."""
import asyncio
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaDocument, MessageMediaPhoto,
    ReplyInlineMarkup, ReplyKeyboardMarkup,
    KeyboardButtonCallback, KeyboardButtonUrl,
    DocumentAttributeFilename,
)

API_ID   = 29846874
API_HASH = "7fbb5d56195c65f83d65f3d850abc72e"
BOT      = "@MedHelpRobot_bot"


async def main():
    client = TelegramClient("med_scraper", API_ID, API_HASH)
    await client.start()

    print("=== Last 50 messages from the bot ===\n")
    async for msg in client.iter_messages(BOT, limit=50):
        direction = "ME →" if msg.out else "BOT →"
        text_preview = (msg.text or "")[:80].replace("\n", " ")

        media_info = ""
        if isinstance(msg.media, MessageMediaDocument):
            doc = msg.media.document
            name_attr = next(
                (a for a in doc.attributes if isinstance(a, DocumentAttributeFilename)), None
            )
            fname = name_attr.file_name if name_attr else "?"
            media_info = f"  [DOCUMENT: {fname}, {doc.size//1024} KB, mime={doc.mime_type}]"
        elif isinstance(msg.media, MessageMediaPhoto):
            media_info = "  [PHOTO]"
        elif msg.media:
            media_info = f"  [MEDIA: {type(msg.media).__name__}]"

        buttons_info = ""
        if msg.reply_markup:
            if isinstance(msg.reply_markup, ReplyInlineMarkup):
                btns = []
                for row in msg.reply_markup.rows:
                    for btn in row.buttons:
                        if isinstance(btn, KeyboardButtonCallback):
                            btns.append(f"[CB:{btn.text}]")
                        elif isinstance(btn, KeyboardButtonUrl):
                            btns.append(f"[URL:{btn.text}→{btn.url}]")
                        else:
                            btns.append(f"[{btn.text}]")
                buttons_info = "  BUTTONS: " + " | ".join(btns)
            elif isinstance(msg.reply_markup, ReplyKeyboardMarkup):
                btns = []
                for row in msg.reply_markup.rows:
                    for btn in row.buttons:
                        btns.append(btn.text)
                buttons_info = "  KEYBOARD: " + " | ".join(btns)

        print(f"{msg.id:6d} {direction} {text_preview}{media_info}{buttons_info}")

    # Also send /start fresh and capture the response
    print("\n=== Sending /start now and waiting 5s ===")
    await client.send_message(BOT, "/start")
    await asyncio.sleep(5)
    async for msg in client.iter_messages(BOT, limit=5):
        if msg.out:
            break
        text_preview = (msg.text or "")[:200].replace("\n", " ")
        print(f"  Response: {text_preview}")
        if msg.reply_markup and isinstance(msg.reply_markup, ReplyInlineMarkup):
            for row in msg.reply_markup.rows:
                for btn in row.buttons:
                    print(f"    Button: [{btn.text}] type={type(btn).__name__}",
                          getattr(btn, 'data', ''), getattr(btn, 'url', ''))

    await client.disconnect()


asyncio.run(main())
