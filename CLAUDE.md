# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Note: a parent-workspace `D:\!2026\AI\Code\CLAUDE.md` exists but does not list this
> project — it predates it. This file is authoritative for this repo. (The "Communication
> is in Russian" workspace convention still applies to user interaction.)

## What this is

Two standalone Python scripts (stdlib only, Python 3.8+, no dependencies, no build step,
no tests) that convert a **Telegram chat/channel export** into an **Obsidian vault** —
one Markdown note per message. Pick the script that matches your export format:

- `build_from_html.py` — input is the **HTML** export (`messages*.html` + media folders).
- `build_vault.py` — input is the **machine-readable JSON** export (`result.json` + media).

## Run

```powershell
python build_from_html.py "D:\Exports\ChatExport_2026-06-10" --channel mychannel
python build_vault.py     "D:\Exports\ChatExport_2026-06-10" --channel mychannel
# build_vault.py also accepts the result.json file directly
```

There is no test suite or linter. Verify changes by running a script against a real export
and inspecting the generated `Posts/*.md`, then re-running to confirm idempotency (below).
`--channel` only affects `t.me/<channel>/<id>` URLs and self-link recognition; omitted → a
neutral `channel` placeholder.

## Critical: the scripts write one level UP

`TOOLS_DIR = dirname(__file__)` and `VAULT = dirname(TOOLS_DIR)`. Output (`Posts/`,
`attachments/`, `_Analytics/`, and a `README.md` counter update) is created **in the parent
of the script's folder**, not in the script folder or the export folder. The intended
deployment is: scripts live in a `_tools/` sub-folder of an Obsidian vault, and they fill the
vault around them. Keep this contract when editing path logic.

## The two scripts are parallel implementations of ONE output contract

Both must emit the **same note format** so a vault can be built from either export type.
When you change the note layout, YAML front matter, the `_Analytics/Post index.md` table,
or the `README.md` counter regexes, **change both files** or they drift. Shared invariants:

- Note filename: `Posts/YYYY-MM-DD idNNNNN.md` (`note_name`).
- Front matter keys: `tg_id, date, channel, url, type, media, parsed: false, tags: [post, unparsed]`,
  plus optional `reply_to` / `forwarded_from` / `author` / `edited`.
- Body: `# Post #id`, `⏮️ Prev · Next ⏭️` nav line (top and bottom), reply marker, text,
  media block, "Open in Telegram" link.
- Posts are sorted into reading order by `(date, id)`; nav links point to chronological
  neighbours in that sorted sequence.
- Service messages are skipped; completely empty posts are skipped.

## Idempotency / the `## 🔍 Analysis` contract

Re-running rewrites the generated body in place but **preserves the user's notes**. The
mechanism (`keep_analysis` / `ANALYSIS_HEADER = "## 🔍 Analysis"`): before writing, read the
existing note and splice back everything from the `## 🔍 Analysis` marker onward. Anything a
user writes ABOVE that marker is generated content and will be overwritten. Do not break this
when changing how notes are written — always read the old file first and re-attach the tail.

## Where the two scripts legitimately differ

- **Parsing:** `build_from_html.py` scrapes HTML with regex (`MSG_RE` splits message blocks,
  then `extract_*` helpers); `build_vault.py` reads structured JSON and renders
  `text_entities` into Markdown.
- **Date handling (HTML only):** grouped/"joined" messages have no per-message date in the
  HTML, so the date is **inherited from the previous message** (`last_dt`). The HTML script
  runs in 3 passes: (1) collect blocks + build the `id→note_name` map, (2) extract fields and
  sort, (3) write notes with neighbour links.
- **Internal links → wikilinks:** the HTML script resolves `t.me/<channel>/<id>` links and
  replies to `[[wikilinks]]` using `id_map`; the JSON script currently renders replies as a
  plain `#id` reference (no `id_map` lookup).
- **Media filenames in `attachments/`:** HTML keeps the original basename; JSON prefixes it
  with `msg_id_` to avoid collisions. Missing media (hit export size limit) becomes a
  `> [!missing]` callout in both.

## Conventions

- All files written UTF-8 with `newline="\n"`; inputs read with `utf-8-sig` to tolerate a BOM.
- `sys.stdout.reconfigure(encoding="utf-8")` guards against the cp1252 Windows console.
