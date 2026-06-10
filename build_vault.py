# -*- coding: utf-8 -*-
"""
build_vault.py — turns a Telegram export (result.json) into Obsidian notes.

Usage:
    python build_vault.py "PATH\\TO\\ChatExport_2026-..."         # folder with result.json
    python build_vault.py "PATH\\TO\\result.json"                  # the file directly
    python build_vault.py "PATH\\TO\\ChatExport_..." --channel mychannel

What it does:
  * reads result.json (the machine-readable JSON export);
  * creates one note per post in  ../Posts/YYYY-MM-DD idNNNNN.md;
  * copies media into ../attachments/ and embeds it in the note;
  * generates ../_Analytics/Post index.md;
  * updates the counters in ../README.md.

Re-run safety:
  The verbatim text and metadata are always rewritten, BUT anything you added
  under the "## 🔍 Analysis" section is kept (read back from the old note).

The --channel option is only used to build t.me URLs; if omitted, a neutral
placeholder is used.
"""
import sys, os, json, shutil, re
from datetime import datetime

# the Windows console is sometimes cp1252 — print as UTF-8 so non-ASCII won't crash
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── paths ─────────────────────────────────────────────────────────────────────
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT     = os.path.dirname(TOOLS_DIR)                 # vault root
POSTS_DIR = os.path.join(VAULT, "Posts")
ATTACH    = os.path.join(VAULT, "attachments")
ANALYTICS = os.path.join(VAULT, "_Analytics")
README    = os.path.join(VAULT, "README.md")

CHANNEL_USERNAME = "channel"          # overridden by --channel
ANALYSIS_HEADER  = "## 🔍 Analysis"   # marker of the user's section

# ── argument parsing ──────────────────────────────────────────────────────────
def parse_args(argv):
    src, channel = None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--channel", "-c"):
            i += 1
            channel = argv[i] if i < len(argv) else None
        elif a.startswith("--channel="):
            channel = a.split("=", 1)[1]
        elif src is None:
            src = a
        i += 1
    return src, channel

def resolve_input(arg):
    if os.path.isdir(arg):
        return os.path.join(arg, "result.json"), arg
    if os.path.isfile(arg):
        return arg, os.path.dirname(arg)
    sys.exit(f"Not found: {arg}")

# ── render text from text_entities (verbatim, with markdown) ──────────────────
def render_entities(msg):
    ents = msg.get("text_entities")
    if ents:
        out = []
        for e in ents:
            t = e.get("text", "")
            typ = e.get("type")
            if typ in ("bold",):                 out.append(f"**{t}**")
            elif typ in ("italic",):             out.append(f"*{t}*")
            elif typ in ("code",):               out.append(f"`{t}`")
            elif typ in ("pre",):                out.append(f"\n```\n{t}\n```\n")
            elif typ in ("strikethrough",):      out.append(f"~~{t}~~")
            elif typ in ("underline",):          out.append(f"<u>{t}</u>")
            elif typ in ("spoiler",):            out.append(f"||{t}||")
            elif typ in ("text_link",):          out.append(f"[{t}]({e.get('href','')})")
            elif typ in ("blockquote",):
                out.append("\n" + "\n".join("> " + ln for ln in t.split("\n")) + "\n")
            else:                                out.append(t)  # plain, link, mention, hashtag, ...
        return "".join(out)
    # fallback: the "text" field may be a string or a list
    txt = msg.get("text", "")
    if isinstance(txt, str):
        return txt
    parts = []
    for p in txt:
        parts.append(p if isinstance(p, str) else p.get("text", ""))
    return "".join(parts)

# ── media ─────────────────────────────────────────────────────────────────────
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

def collect_media(msg):
    """Return a list of candidate paths (relative to the export)."""
    paths = []
    for key in ("photo", "file"):
        v = msg.get(key)
        if v and isinstance(v, str):
            paths.append(v)
    # stickers/animations also live in 'file'; we skip the thumbnail to avoid dupes
    return paths

def copy_media(rel_path, export_dir, msg_id):
    src = os.path.join(export_dir, rel_path.replace("/", os.sep))
    if not os.path.isfile(src):
        return None, False  # file not exported (e.g. it hit the size limit)
    base = os.path.basename(src)
    dest_name = f"{msg_id}_{base}"
    dest = os.path.join(ATTACH, dest_name)
    if not os.path.isfile(dest):
        shutil.copy2(src, dest)
    is_img = os.path.splitext(base)[1].lower() in IMG_EXT
    return dest_name, is_img

def media_block(msg, export_dir, msg_id):
    lines = []
    for rel in collect_media(msg):
        name, is_img = copy_media(rel, export_dir, msg_id)
        if name is None:
            lines.append(f"> [!missing] Media not exported: `{rel}`")
        elif is_img:
            lines.append(f"![[attachments/{name}]]")
        else:
            mt = msg.get("media_type", "file")
            lines.append(f"📎 `{mt}` → [[attachments/{name}]]")
    if "sticker_emoji" in msg:
        lines.append(f"_sticker: {msg['sticker_emoji']}_")
    if "poll" in msg:
        poll = msg["poll"]
        lines.append(f"> [!question] Poll: {poll.get('question','')}")
        for a in poll.get("answers", []):
            lines.append(f"> - {a.get('text','')}  ({a.get('voters',0)})")
    return "\n".join(lines)

# ── note file name ────────────────────────────────────────────────────────────
def note_name(msg):
    dt = parse_date(msg)
    return f"{dt.strftime('%Y-%m-%d')} id{int(msg['id']):05d}.md"

def nav_line(prev_name, next_name):
    # chronological slider: links to neighbouring posts
    left  = f"[[{prev_name[:-3]}|⏮️ Prev]]"  if prev_name else "⏮️ _start_"
    right = f"[[{next_name[:-3]}|Next ⏭️]]"  if next_name else "_end_ ⏭️"
    return f"{left} · {right}"

def parse_date(msg):
    # the "date" field is local time as Telegram shows it; use it
    d = msg.get("date")
    if d:
        try:
            return datetime.fromisoformat(d)
        except ValueError:
            pass
    return datetime.fromtimestamp(int(msg["date_unixtime"]))

# ── keep the user's section on re-run ─────────────────────────────────────────
def keep_analysis(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        content = f.read()
    idx = content.find(ANALYSIS_HEADER)
    return content[idx:] if idx != -1 else None

# ── build a note ──────────────────────────────────────────────────────────────
def build_note(msg, export_dir, prev_name=None, next_name=None):
    mid = int(msg["id"])
    dt  = parse_date(msg)
    text = render_entities(msg).rstrip()
    media = media_block(msg, export_dir, mid)
    nav = nav_line(prev_name, next_name)

    has_media = bool(collect_media(msg))
    fm_media = "[" + ", ".join(filter(None, [
        msg.get("media_type", "photo" if msg.get("photo") else None)
    ])) + "]" if has_media else "[]"

    fm = [
        "---",
        f"tg_id: {mid}",
        f"date: {dt.isoformat()}",
        f"channel: {CHANNEL_USERNAME}",
        f"url: https://t.me/{CHANNEL_USERNAME}/{mid}",
        f"type: {msg.get('type','message')}",
        f"media: {fm_media}",
    ]
    if msg.get("reply_to_message_id"):
        fm.append(f"reply_to: {msg['reply_to_message_id']}")
    if msg.get("forwarded_from"):
        fm.append(f"forwarded_from: \"{msg['forwarded_from']}\"")
    if msg.get("edited"):
        fm.append(f"edited: {msg['edited']}")
    fm += ["parsed: false", "tags: [post, unparsed]", "---", ""]

    body = [f"# Post #{mid} · {dt.strftime('%d.%m.%Y %H:%M')}", "", nav, ""]
    if msg.get("forwarded_from"):
        body.append(f"> [!quote] Forwarded from: {msg['forwarded_from']}\n")
    if msg.get("reply_to_message_id"):
        body.append(f"↩️ Reply to #{msg['reply_to_message_id']}\n")
    if text:
        body += [text, ""]
    if media:
        body += [media, ""]
    body += ["---", nav, "", f"🔗 [Open in Telegram](https://t.me/{CHANNEL_USERNAME}/{mid})", ""]

    note = "\n".join(fm) + "\n".join(body) + "\n"

    # keep the old analysis section if there was one
    path = os.path.join(POSTS_DIR, note_name(msg))
    old = keep_analysis(path)
    if old:
        note += "\n" + old.rstrip() + "\n"
    else:
        note += f"\n{ANALYSIS_HEADER}\n\n_not analyzed yet_\n"
    return path, note, dt, text

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    global CHANNEL_USERNAME
    src, channel = parse_args(sys.argv[1:])
    if not src:
        sys.exit('Give the export path: python build_vault.py "...\\ChatExport_..." [--channel name]')
    if channel:
        CHANNEL_USERNAME = channel.lstrip("@")
    json_path, export_dir = resolve_input(src)

    with open(json_path, encoding="utf-8-sig") as f:   # tolerate a BOM
        data = json.load(f)
    messages = data.get("messages", data if isinstance(data, list) else [])

    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(ATTACH, exist_ok=True)
    os.makedirs(ANALYTICS, exist_ok=True)

    n_service = sum(1 for m in messages if m.get("type") == "service")
    posts = [m for m in messages if m.get("type") == "message"]
    posts.sort(key=lambda m: (parse_date(m), int(m["id"])))   # reading order
    seq = [note_name(m) for m in posts]

    index_rows, n_msg = [], 0
    for i, msg in enumerate(posts):
        prev_name = seq[i - 1] if i > 0 else None
        next_name = seq[i + 1] if i < len(seq) - 1 else None
        path, note, dt, text = build_note(msg, export_dir, prev_name, next_name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(note)
        n_msg += 1
        preview = re.sub(r"\s+", " ", text).strip()[:80]
        mark = "🖼️" if msg.get("photo") else ("📎" if msg.get("file") else "")
        index_rows.append((dt, int(msg["id"]), preview, mark))

    write_index(index_rows)
    update_readme(n_msg)
    print(f"Done. Posts: {n_msg}. Service skipped: {n_service}.")
    print(f"Notes: {POSTS_DIR}")
    print(f"Media: {ATTACH}")

def write_index(rows):
    rows.sort(key=lambda r: r[0])
    out = ["---", "type: analytics", f"updated: {datetime.now():%Y-%m-%d}", "---", "",
           "# 🗂️ Post index", "",
           f"Total: **{len(rows)}**. Auto-generated — no need to edit by hand.", "",
           "| Date | ID | Text start | Media |",
           "|------|----|----|----|"]
    for dt, mid, preview, mark in rows:
        link = f"[[{dt.strftime('%Y-%m-%d')} id{mid:05d}]]"
        safe = preview.replace("|", "\\|")
        out.append(f"| {dt:%Y-%m-%d %H:%M} | {link} | {safe} | {mark} |")
    with open(os.path.join(ANALYTICS, "Post index.md"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")

def update_readme(n):
    if not os.path.isfile(README):
        return
    with open(README, encoding="utf-8") as f:
        c = f.read()
    c = re.sub(r"total_posts: \d+", f"total_posts: {n}", c)
    c = re.sub(r"updated: [\d-]+", f"updated: {datetime.now():%Y-%m-%d}", c, count=1)
    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(c)

if __name__ == "__main__":
    main()
