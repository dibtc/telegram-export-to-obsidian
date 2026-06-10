# telegram-export-to-obsidian

Two small, dependency-free Python scripts that turn a **Telegram chat/channel export**
into a browsable **Obsidian vault** — one Markdown note per message, with media
embedded, replies and internal links turned into `[[wikilinks]]`, and an
auto-generated post index.

| Script | Input | Use it when |
|--------|-------|-------------|
| `build_from_html.py` | the **HTML** export (`messages*.html` + media folders) | you exported with *Telegram Desktop → Export chat history → HTML* |
| `build_vault.py` | the **machine-readable JSON** export (`result.json` + media) | you exported with *Telegram Desktop → Export chat history → Machine-readable JSON* |

Both produce the **same vault layout** and share the same conventions, so pick the
one that matches the format you exported. No third-party packages are required —
they use only the Python standard library (Python 3.8+).

## What you get

For every message a note is written to `Posts/YYYY-MM-DD idNNNNN.md` containing:

- **YAML front matter** — `tg_id`, `date`, `channel`, `url`, `type`, `media`,
  optional `reply_to` / `forwarded_from` / `author`, `parsed: false`, `tags`.
- The **verbatim message text**, with Telegram formatting mapped to Markdown
  (bold, italic, strikethrough, code, spoilers `||...||`, block quotes, links).
- **Embedded media** copied into `attachments/` — images via `![[...]]`, audio/video
  via the Obsidian player, other files as a link.
- **Navigation** — `⏮️ Prev · Next ⏭️` links to the chronologically neighbouring
  notes, so you can read the channel like a book.
- **Relationships** — replies and internal `t.me/<channel>/<id>` links become
  `[[wikilinks]]` between notes.
- A personal **`## 🔍 Analysis`** section at the bottom for your own notes.

It also generates `_Analytics/Post index.md` (an auto table of every post) and
updates the post counter in the vault `README.md` if one exists.

### Resulting folder layout

```
My Vault/                     ← your Obsidian vault root
├── _tools/                   ← put the scripts here (any sub-folder name works)
│   ├── build_from_html.py
│   └── build_vault.py
├── Posts/                    ← one note per message  (generated)
├── attachments/             ← copied media           (generated)
├── _Analytics/
│   └── Post index.md         ← auto post index        (generated)
└── README.md                 ← optional; counters auto-updated
```

> **Important:** the scripts write **one level up** from where they live. The output
> folders (`Posts/`, `attachments/`, `_Analytics/`) are created **next to the folder
> that contains the script** — i.e. in the parent directory. So keep the scripts in a
> sub-folder of the vault you want to fill (for example `_tools/`), not in the vault
> root itself.

## Usage

### 1. Export your chat from Telegram Desktop

*Settings → Advanced → Export Telegram data*, or right-click a chat →
**Export chat history**. Choose **HTML** or **Machine-readable JSON**, and include
the media you want. You'll get a folder like `ChatExport_2026-06-10` containing
`messages.html` (or `result.json`) plus `photos/`, `video_files/`, `files/`, etc.

### 2. Place the scripts in your vault

Create a sub-folder (e.g. `_tools`) inside your Obsidian vault and copy
`build_from_html.py` and `build_vault.py` into it.

### 3. Run the script that matches your export

From the script's folder:

```bash
# HTML export
python build_from_html.py "PATH/TO/ChatExport_2026-06-10"

# JSON export — point at the folder or directly at result.json
python build_vault.py "PATH/TO/ChatExport_2026-06-10"
python build_vault.py "PATH/TO/ChatExport_2026-06-10/result.json"
```

On Windows / PowerShell:

```powershell
python "build_from_html.py" "D:\Exports\ChatExport_2026-06-10"
```

### 4. (Optional) set the channel username

The `channel` is only used to build `https://t.me/<channel>/<id>` links and to
recognise self-links to the same channel. Pass it to get correct Telegram URLs:

```bash
python build_from_html.py "PATH/TO/Export" --channel mychannel
python build_vault.py     "PATH/TO/Export" --channel mychannel
```

If omitted, a neutral `channel` placeholder is used.

### 5. Open the parent folder as a vault in Obsidian

Open the folder that contains your `_tools/` sub-folder. You'll see `Posts/`,
`attachments/` and `_Analytics/`. Start reading from any note and use the
`⏮️ Prev · Next ⏭️` links, or open `_Analytics/Post index.md` for the full list.

## Re-running is safe

Both scripts are **idempotent**. Re-run them after a fresh export (e.g. when new
messages appeared) and notes are rebuilt in place. The message body and metadata
are always overwritten, **but everything you wrote under the `## 🔍 Analysis`
marker is preserved** — it is read back from the existing note and re-attached.

> Keep your own notes/comments **only** under `## 🔍 Analysis`. Anything written
> above that marker is part of the generated body and will be overwritten on the
> next run.

## Notes & limitations

- Service messages (joins, pinned, etc.) are skipped.
- For the HTML export, dates are inherited from the previous message for grouped
  ("joined") messages, matching how Telegram displays them.
- Media that wasn't actually exported (e.g. it hit a size limit) is flagged in the
  note with a `> [!missing]` callout instead of breaking the link.
- Times are kept as **local time exactly as Telegram shows them** (no timezone
  conversion).

## License

[MIT](LICENSE)
