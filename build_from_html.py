# -*- coding: utf-8 -*-
"""
build_from_html.py — turns a Telegram HTML export (messages*.html + media)
into Obsidian notes, preserving relationships (replies), dates, time and media.

Usage:
    python build_from_html.py "PATH\\TO\\Telegram Export"
    python build_from_html.py "PATH\\TO\\Telegram Export" --channel mychannel

The export folder must contain messages.html (and/or messages2.html, ...) and
the sub-folders photos/ video_files/ files/ stickers/.

  * one note per post — ../Posts/YYYY-MM-DD idNNNNN.md;
  * media is copied into ../attachments/ and embedded;
  * replies (In reply to) become [[...]] links between notes;
  * internal t.me/<channel>/<id> links also become [[...]] links;
  * ../_Analytics/Post index.md is generated, the counter in README.md updated.

Re-running is safe: anything you wrote below the '## 🔍 Analysis' marker is kept.

The --channel option is only used to build t.me URLs and to recognize self-links
to the same channel; if omitted, a neutral placeholder is used.
"""
import sys, os, re, glob, html, shutil
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT     = os.path.dirname(TOOLS_DIR)
POSTS_DIR = os.path.join(VAULT, "Posts")
ATTACH    = os.path.join(VAULT, "attachments")
ANALYTICS = os.path.join(VAULT, "_Analytics")
README    = os.path.join(VAULT, "README.md")

CHANNEL_USERNAME = "channel"          # overridden by --channel
ANALYSIS_HEADER  = "## 🔍 Analysis"
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MEDIA_DIRS = ("photos", "video_files", "files", "stickers", "voice_messages",
              "round_video_messages", "video_messages")

# ── helpers ───────────────────────────────────────────────────────────────────
def read(path):
    return open(path, encoding="utf-8-sig").read()

def parse_dt(title):
    # "26.05.2022 14:02:07 UTC+03:00"  → datetime (no tz, local as in Telegram)
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2}):(\d{2})", title)
    if not m:
        return None
    d, mo, y, h, mi, s = map(int, m.groups())
    return datetime(y, mo, d, h, mi, s)

def note_name(dt, mid):
    return f"{dt.strftime('%Y-%m-%d')} id{mid:05d}.md"

def nav_line(prev_name, next_name):
    # chronological slider: links to neighbouring posts
    left  = f"[[{prev_name[:-3]}|⏮️ Prev]]"  if prev_name else "⏮️ _start_"
    right = f"[[{next_name[:-3]}|Next ⏭️]]"  if next_name else "_end_ ⏭️"
    return f"{left} · {right}"

def keep_analysis(path):
    if not os.path.isfile(path):
        return None
    c = read(path)
    i = c.find(ANALYSIS_HEADER)
    return c[i:] if i != -1 else None

# ── split HTML into message blocks ────────────────────────────────────────────
MSG_RE = re.compile(r'<div class="message ([^"]*)" id="message(-?\d+)">(.*?)(?=<div class="message |</div>\s*</div>\s*</body>|$)', re.S)

def iter_blocks(htmls):
    for h in htmls:
        raw = read(h)
        for m in MSG_RE.finditer(raw):
            yield m.group(1), int(m.group(2)), m.group(3)

# ── extract fields from a block ───────────────────────────────────────────────
def extract_date(block):
    m = re.search(r'date details" title="([^"]+)"', block)
    return parse_dt(m.group(1)) if m else None

def extract_reply(block):
    m = re.search(r'#go_to_message(\d+)', block)
    return int(m.group(1)) if m else None

def extract_signature(block):
    m = re.search(r'<div class="signature details">\s*(.*?)\s*</div>', block, re.S)
    return html.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip()) if m else None

def extract_media(block):
    paths = []
    for d in MEDIA_DIRS:
        for href in re.findall(r'(?:href|src)="(' + d + r'/[^"]+)"', block):
            href = html.unescape(href)
            if href not in paths:
                paths.append(href)
    return paths

def extract_text(block, id_map):
    m = re.search(r'<div class="text">(.*?)</div>', block, re.S)
    if not m:
        return ""
    t = m.group(1)
    # links -> markdown or internal [[...]]
    def link_repl(mm):
        href, inner = html.unescape(mm.group(1)).strip(), mm.group(2)
        inner_txt = html.unescape(re.sub(r'<[^>]+>', '', inner)).strip()
        # empty/anchor href (hashtags, mentions) — keep as plain text
        if not href or href.startswith("#") or href.lower().startswith("javascript"):
            return inner_txt
        im = re.search(r't\.me/(?:c/)?(?:' + re.escape(CHANNEL_USERNAME) + r'|\d+)/(\d+)', href)
        if im:
            tid = int(im.group(1))
            if tid in id_map:
                return f"[[{id_map[tid][:-3]}|{inner_txt or '#'+str(tid)}]]"
        if not inner_txt:                 # icon-link without text — show the URL
            return f"<{href}>"
        return f"[{inner_txt}]({href})"
    t = re.sub(r'<a href="([^"]*)"[^>]*>(.*?)</a>', link_repl, t, flags=re.S)
    # formatting
    t = re.sub(r'<br\s*/?>', '\n', t)
    t = re.sub(r'</?(strong|b)>', '**', t)
    t = re.sub(r'</?(em|i)>', '*', t)
    t = re.sub(r'</?(s|del|strike)>', '~~', t)
    t = re.sub(r'</?code>', '`', t)
    t = re.sub(r'<pre>(.*?)</pre>', lambda x: f"\n```\n{x.group(1)}\n```\n", t, flags=re.S)
    t = re.sub(r'<span class="tg-spoiler">(.*?)</span>', r'||\1||', t, flags=re.S)
    t = re.sub(r'<blockquote>(.*?)</blockquote>',
               lambda x: "\n" + "\n".join("> " + ln for ln in x.group(1).split("\n")) + "\n",
               t, flags=re.S)
    t = re.sub(r'<[^>]+>', '', t)          # drop remaining tags
    t = html.unescape(t)
    return t.strip()

def copy_media(rel, export_dir):
    src = os.path.join(export_dir, rel.replace("/", os.sep))
    if not os.path.isfile(src):
        return None, False
    base = os.path.basename(src)
    dest = os.path.join(ATTACH, base)
    if not os.path.isfile(dest):
        shutil.copy2(src, dest)
    is_img = os.path.splitext(base)[1].lower() in IMG_EXT
    return base, is_img

AV_EXT = {".mp3", ".ogg", ".opus", ".wav", ".m4a", ".flac",
          ".mp4", ".webm", ".mov", ".mkv", ".ogv", ".3gp"}

def media_block(paths, export_dir):
    lines = []
    for rel in paths:
        base = os.path.basename(rel)
        # skip a standalone thumbnail: we embed the file itself with a player
        if "_thumb." in base.lower() and any(
                os.path.basename(p) == base.replace("_thumb.jpg", "") for p in paths):
            continue
        name, is_img = copy_media(rel, export_dir)
        ext = os.path.splitext(base)[1].lower()
        if name is None:
            lines.append(f"> [!missing] Media not exported: `{rel}`")
        elif is_img:
            lines.append(f"![[attachments/{name}]]")
        elif ext in AV_EXT:
            kind = "🎬 video" if ext in {".mp4", ".webm", ".mov", ".mkv", ".ogv", ".3gp"} else "🔊 audio"
            lines.append(f"{kind}: ![[attachments/{name}]]")
        else:
            kind = rel.split("/", 1)[0]
            lines.append(f"📎 `{kind}` → [[attachments/{name}]]")
    return "\n".join(lines)

# ── build a note ──────────────────────────────────────────────────────────────
def build_note(mid, dt, text, paths, reply_id, signature, id_map, export_dir,
               prev_name=None, next_name=None):
    media = media_block(paths, export_dir)
    has_media = bool(paths)
    nav = nav_line(prev_name, next_name)

    fm = ["---", f"tg_id: {mid}", f"date: {dt.isoformat()}",
          f"channel: {CHANNEL_USERNAME}",
          f"url: https://t.me/{CHANNEL_USERNAME}/{mid}",
          "type: message",
          f"media: {'true' if has_media else 'false'}"]
    if reply_id:
        fm.append(f"reply_to: {reply_id}")
    if signature:
        fm.append(f"author: \"{signature}\"")
    fm += ["parsed: false", "tags: [post, unparsed]", "---", ""]

    body = [f"# Post #{mid} · {dt.strftime('%d.%m.%Y %H:%M')}", "", nav, ""]
    if reply_id and reply_id in id_map:
        body.append(f"↩️ Reply to [[{id_map[reply_id][:-3]}|#{reply_id}]]\n")
    elif reply_id:
        body.append(f"↩️ Reply to #{reply_id}\n")
    if text:
        body += [text, ""]
    if media:
        body += [media, ""]
    if signature:
        body += [f"_— {signature}_", ""]
    body += ["---", nav, "", f"🔗 [Open in Telegram](https://t.me/{CHANNEL_USERNAME}/{mid})", ""]

    note = "\n".join(fm) + "\n".join(body) + "\n"
    path = os.path.join(POSTS_DIR, note_name(dt, mid))
    old = keep_analysis(path)
    note += ("\n" + old.rstrip() + "\n") if old else f"\n{ANALYSIS_HEADER}\n\n_not analyzed yet_\n"
    return path, note

# ── argument parsing ──────────────────────────────────────────────────────────
def parse_args(argv):
    export_dir, channel = None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--channel", "-c"):
            i += 1
            channel = argv[i] if i < len(argv) else None
        elif a.startswith("--channel="):
            channel = a.split("=", 1)[1]
        elif export_dir is None:
            export_dir = a
        i += 1
    return export_dir, channel

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    global CHANNEL_USERNAME
    export_dir, channel = parse_args(sys.argv[1:])
    if not export_dir:
        sys.exit('Give the export folder: python build_from_html.py "...\\Telegram Export" [--channel name]')
    if channel:
        CHANNEL_USERNAME = channel.lstrip("@")

    htmls = sorted(glob.glob(os.path.join(export_dir, "messages*.html")))
    if not htmls:
        sys.exit(f"No messages*.html found in {export_dir}")

    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(ATTACH, exist_ok=True)
    os.makedirs(ANALYTICS, exist_ok=True)

    # Pass 1: collect posts, inherit dates for joined messages, build id→name
    blocks, last_dt, id_map = [], None, {}
    n_service = 0
    for cls, mid, block in iter_blocks(htmls):
        if "service" in cls:
            n_service += 1
            continue
        dt = extract_date(block) or last_dt
        if dt is None:
            continue
        last_dt = dt
        blocks.append((mid, dt, block))
        id_map[mid] = note_name(dt, mid)

    # Pass 2: prepare non-empty posts and order them chronologically
    prepared = []
    for mid, dt, block in blocks:
        text     = extract_text(block, id_map)
        paths    = extract_media(block)
        reply_id = extract_reply(block)
        sign     = extract_signature(block)
        if not text and not paths:      # completely empty block — skip
            continue
        prepared.append((mid, dt, text, paths, reply_id, sign))
    prepared.sort(key=lambda p: (p[1], p[0]))            # reading order = (date, id)
    seq = [note_name(dt, mid) for (mid, dt, *_rest) in prepared]

    # Pass 3: write notes with ⏮️/⏭️ slider links to neighbours
    index_rows = []
    for i, (mid, dt, text, paths, reply_id, sign) in enumerate(prepared):
        prev_name = seq[i - 1] if i > 0 else None
        next_name = seq[i + 1] if i < len(seq) - 1 else None
        path, note = build_note(mid, dt, text, paths, reply_id, sign,
                                id_map, export_dir, prev_name, next_name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(note)
        preview = re.sub(r"\s+", " ", text).strip()[:80]
        mark = "🖼️" if any("photos/" in p for p in paths) else ("📎" if paths else "")
        index_rows.append((dt, mid, preview, mark))

    write_index(index_rows)
    update_readme(len(index_rows))
    print(f"Done. Posts written: {len(index_rows)}. Service skipped: {n_service}.")
    print(f"Notes: {POSTS_DIR}")
    print(f"Media: {ATTACH}")

def write_index(rows):
    rows.sort(key=lambda r: (r[0], r[1]))
    out = ["---", "type: analytics", f"updated: {datetime.now():%Y-%m-%d}", "---", "",
           "# 🗂️ Post index", "",
           f"Total: **{len(rows)}**. Auto-generated — no need to edit by hand.", "",
           "| Date | ID | Text start | Media |", "|------|----|----|----|"]
    for dt, mid, preview, mark in rows:
        link = f"[[{dt.strftime('%Y-%m-%d')} id{mid:05d}]]"
        out.append(f"| {dt:%Y-%m-%d %H:%M} | {link} | {preview.replace('|','\\|')} | {mark} |")
    with open(os.path.join(ANALYTICS, "Post index.md"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")

def update_readme(n):
    if not os.path.isfile(README):
        return
    c = read(README)
    c = re.sub(r"total_posts: \d+", f"total_posts: {n}", c)
    c = re.sub(r"updated: [\d-]+", f"updated: {datetime.now():%Y-%m-%d}", c, count=1)
    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(c)

if __name__ == "__main__":
    main()
