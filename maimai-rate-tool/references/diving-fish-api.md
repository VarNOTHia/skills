# Diving-Fish API Notes

Base URL:

```text
https://www.diving-fish.com/api/maimaidxprober
```

## Auth

For this skill, use `Import-Token`:

```http
Import-Token: user_import_token
```

Developer-Token is for developer query endpoints and is not used for score upload.

## Endpoints

Validate token:

```http
GET /player/validate
```

Query full records for the token owner:

```http
GET /player/records
```

Fetch music data:

```http
GET /music_data
```

Upload records:

```http
POST /player/update_records
Content-Type: application/json
```

Request body is a JSON array of records. Upload is incremental upsert; records not included in the request are left untouched.

## Upload Fields

Required/effective fields:

- `title`: exact Diving-Fish music title.
- `type`: `SD` or `DX`.
- `level_index`: Basic `0`, Advanced `1`, Expert `2`, Master `3`, Re:MASTER `4`.
- `achievements`: numeric achievement percentage.
- `dxScore`: integer single-chart DX Score.
- `fc`: `fc`, `fcp`, `ap`, `app`, or empty.
- `fs`: `sync`, `fs`, `fsp`, `fsd`, `fsdp`, or empty.

The backend resolves `chart_id` from `title + type + level_index`. It does not use `song_id` in uploads.

## DX Score Calculation From Judgements

If a result screenshot includes judgement counts, calculate single-chart DX Score as:

```text
criticalPerfect * 3 + perfect * 2 + great
```

Good and miss do not add DX Score points.

Do not confuse single-chart `dxScore` with the player's DX Rating shown on the result screen or profile.
