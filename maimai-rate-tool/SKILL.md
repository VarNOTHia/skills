---
name: maimai-rate-tool
description: Use when a user wants to identify maimai DX scores from screenshots, match songs against Diving-Fish music data, query their Diving-Fish records, or upload confirmed maimai DX records with an Import-Token. Enforces preview-before-upload and safe Import-Token handling.
metadata:
  short-description: Identify, match, query, and upload maimai DX scores
---

# maimai-rate-tool

Use this skill for maimai DX score workflows involving Diving-Fish:

- Read a result screenshot and extract song, difficulty, achievements, FC/FS, and judgement table.
- Match the extracted song name to the Diving-Fish music data.
- Query a user's records with their `Import-Token`.
- Upload a confirmed record to `/player/update_records`.

## Safety Rules

1. Never upload on first pass. First show the user:
   - recognized fields,
   - matched music-data entry,
   - the exact JSON that would be uploaded.
2. Upload only after the user explicitly confirms, such as "确认上传" or "上传吧".
3. Use only the user's `Import-Token` for query/upload. Do not ask for Developer-Token; it is not used for uploading.
4. Do not write Import-Token to files, docs, shell history, or command arguments. Prefer `MAIMAI_IMPORT_TOKEN` only for one command invocation, or read it from hidden stdin.
5. Treat screenshots as fallible. If title, difficulty, achievements, or `dxScore` are uncertain, ask for confirmation before upload.
6. If a screenshot shows player DX Rating, do not use it as record `dxScore`.

## Core Concepts

- Upload endpoint: `POST https://www.diving-fish.com/api/maimaidxprober/player/update_records`
- Query endpoint: `GET https://www.diving-fish.com/api/maimaidxprober/player/records`
- Auth header: `Import-Token: <token>`
- Upload is incremental upsert: only submitted records are updated or created.
- The backend matches by `title + type + level_index`, not by `song_id`.

Upload record shape:

```json
{
  "title": "アポカリプスに反逆の焔を焚べろ",
  "type": "DX",
  "level_index": 3,
  "achievements": 100.5681,
  "dxScore": 3022,
  "fc": "",
  "fs": ""
}
```

Difficulty mapping:

- Basic: `0`
- Advanced: `1`
- Expert: `2`
- Master: `3`
- Re:MASTER: `4`

## Screenshot Workflow

1. Use visual inspection to extract:
   - song title,
   - `type` (`SD` or `DX`),
   - difficulty,
   - achievements,
   - FC/FS if visible,
   - judgement counts if visible.
2. Fetch/cache music data if needed:

```bash
node scripts/maimai-rate-tool.js music
```

3. Match the extracted title locally:

```bash
node scripts/maimai-rate-tool.js match --query "recognized title" --type DX --diff master
```

4. If judgement counts are available, calculate `dxScore`:

```bash
node scripts/maimai-rate-tool.js dx-score --judgements '{"tap":[620,192,6,1,3],"hold":[42,12,0,0,0],"slide":[78,0,0,0,0],"touch":[106,0,0,0,0],"break":[18,8,0,0,0]}'
```

Judgement array order is `[criticalPerfect, perfect, great, good, miss]`.

5. Show the user the candidate JSON and wait for confirmation.
6. Upload only after confirmation.

## Token-Safe Upload Pattern

When the user already provided a token in the conversation, avoid putting it in command-line args. Use an interactive shell pattern:

```bash
stty -echo
IFS= read -r TOKEN
stty echo
MAIMAI_IMPORT_TOKEN="$TOKEN" node scripts/maimai-rate-tool.js upload-record --title "..." --type DX --diff master --achievements 100.5681 --dx-score 3022
```

Then provide the token to stdin, followed by a newline.

## Useful Commands

Query record summary:

```bash
MAIMAI_IMPORT_TOKEN="$TOKEN" node scripts/maimai-rate-tool.js records --top 10
```

Upload one record:

```bash
MAIMAI_IMPORT_TOKEN="$TOKEN" node scripts/maimai-rate-tool.js upload-record --title "..." --type DX --diff master --achievements 100.5681 --dx-score 3022 --fc "" --fs ""
```

Upload a JSON file:

```bash
MAIMAI_IMPORT_TOKEN="$TOKEN" node scripts/maimai-rate-tool.js upload-json ./records.json
```

## References

Read `references/diving-fish-api.md` if you need endpoint details, upload field semantics, or common pitfalls.
