"""
Download all PDFs from @MedHelpRobot_bot.

Navigation tree (5 levels deep):
  Semester → Subject → Category → Part → PDF

Uses DFS with a visited-path set to avoid cycles.
"""

import asyncio
import re
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import (
    DocumentAttributeFilename, MessageMediaDocument,
    ReplyKeyboardMarkup, ReplyKeyboardHide,
)

API_ID   = 29846874
API_HASH = "7fbb5d56195c65f83d65f3d850abc72e"
BOT      = "@MedHelpRobot_bot"
MAX_DEPTH = 6

DOWNLOAD_DIR = Path(__file__).parent / "pdfs" / "uploads" / "med_books"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

SKIP_NAME_CONTAINS = {"محذوفات", "فيديوهات"}

already_saved = {f.name for f in DOWNLOAD_DIR.glob("*.pdf")}
collected: list[str] = []

VISITED_FILE = Path(__file__).parent / "visited_labels.json"

def load_visited() -> set[str]:
    if VISITED_FILE.exists():
        import json
        return set(json.loads(VISITED_FILE.read_text(encoding="utf-8")))
    return set()

def save_visited(v: set[str]) -> None:
    import json
    VISITED_FILE.write_text(json.dumps(list(v)), encoding="utf-8")

visited_labels: set[str] = load_visited()


# ── helpers ───────────────────────────────────────────────────────────────────

def _pdf_filename(doc) -> str | None:
    is_pdf = "pdf" in (doc.mime_type or "").lower()
    name_attr = next(
        (a for a in doc.attributes if isinstance(a, DocumentAttributeFilename)), None
    )
    has_pdf_name = name_attr and name_attr.file_name.lower().endswith(".pdf")
    if not is_pdf and not has_pdf_name:
        return None
    raw = name_attr.file_name if name_attr else f"file_{doc.id}.pdf"
    raw = raw.replace("\n", " ").replace("\r", "").strip()
    return re.sub(r'[\\/:*?"<>|]', "_", raw)


async def save_if_pdf(client, msg) -> bool:
    if not isinstance(msg.media, MessageMediaDocument):
        return False
    doc = msg.media.document
    if not doc:
        return False
    fname = _pdf_filename(doc)
    if fname is None:
        return False
    if any(s in fname for s in SKIP_NAME_CONTAINS):
        print(f"    [filter] {fname}")
        return False
    if fname in already_saved:
        print(f"    [have]   {fname}")
        return False
    dest = DOWNLOAD_DIR / fname
    size_mb = doc.size / (1024 * 1024)
    print(f"    ↓ {fname}  ({size_mb:.1f} MB)")
    await client.download_media(msg, file=dest)
    already_saved.add(fname)
    collected.append(fname)
    print(f"    ✓ saved")
    return True


async def get_bot_response(client) -> list:
    """Wait for bot reply and return (messages, keyboard_labels)."""
    await asyncio.sleep(3)
    msgs = []
    labels = []
    async for msg in client.iter_messages(BOT, limit=5):
        if msg.out:
            break
        msgs.append(msg)
        if msg.reply_markup and isinstance(msg.reply_markup, ReplyKeyboardMarkup):
            for row in msg.reply_markup.rows:
                for btn in row.buttons:
                    labels.append(btn.text.strip())
    return msgs, labels


SKIP_LABELS = {
    "go back", "رجوع", "الرجوع",
    "med help بوتات", "❤️ med help ❤️",
}

# Substrings — any label containing one of these is skipped
SKIP_CONTAINS = {
    "فيديو", "يوتيوب", "youtu",
    "برامج",          # D3 animation software
    "بوستر",          # poster graphics
    "دورات",          # video course notes
    "نوط دورات",      # course notes 2025/2026
    "دراسة عملي",     # lab study videos
    "استبيان",        # quiz-format courses
    "محذوفات وزار",   # ministry deletions (not a book)
    "ط غروبنا",       # social media group link
}

def should_skip(label: str) -> bool:
    l = label.strip()
    if l.lower() in {s.lower() for s in SKIP_LABELS}:
        return True
    if any(kw in l for kw in SKIP_CONTAINS):
        return True
    return False


# ── DFS traversal ─────────────────────────────────────────────────────────────

async def explore(client, labels: list, depth: int) -> None:
    """For each button label, send it, collect PDFs/sub-menus, then go back."""
    if depth >= MAX_DEPTH:
        return

    indent = "  " * depth

    for label in labels:
        if should_skip(label):
            continue

        if label in visited_labels:
            continue   # already explored this button globally — silent skip
        visited_labels.add(label)
        save_visited(visited_labels)

        print(f"{indent}→ {label}")
        await client.send_message(BOT, label)
        msgs, sub_labels = await get_bot_response(client)

        # Collect any PDFs the bot sent
        for msg in msgs:
            await save_if_pdf(client, msg)

        # Remove navigation labels from sub-menu
        sub_labels_clean = [l for l in sub_labels if not should_skip(l) and l != label]

        if sub_labels_clean:
            await explore(client, sub_labels_clean, depth + 1)

        # Go back up
        await client.send_message(BOT, "Go Back")
        await asyncio.sleep(2)


# ── main ─────────────────────────────────────────────────────────────────────

async def main():
    # If you have a local SOCKS5 proxy (e.g. from a VPN or browser extension),
    # uncomment the next two lines and set the correct port:
    # import socks
    # proxy = (socks.SOCKS5, "127.0.0.1", 1080)
    # client = TelegramClient("med_scraper", API_ID, API_HASH, proxy=proxy)
    client = TelegramClient("med_scraper", API_ID, API_HASH)
    await client.start()
    print(f"Logged in as: {(await client.get_me()).first_name}")
    print(f"Already on disk: {len(already_saved)} files\n")

    # Start from the main menu
    print("Opening main menu...")
    await client.send_message(BOT, "/start")
    msgs, top_labels = await get_bot_response(client)
    print(f"Top-level options: {top_labels}\n")

    # Explore the full tree
    await explore(client, top_labels, depth=0)

    # ── Final history sweep to catch anything missed ──────────────────────────
    print("\n=== History sweep (3000 messages) ===")
    async for msg in client.iter_messages(BOT, limit=3000):
        if not msg.out:
            await save_if_pdf(client, msg)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*52}")
    print(f"Newly downloaded: {len(collected)}")
    print(f"Total on disk:    {len(already_saved)}")
    print(f"Location: {DOWNLOAD_DIR}\n")
    for f in collected:
        print(f"  • {f}")

    await client.disconnect()


asyncio.run(main())
