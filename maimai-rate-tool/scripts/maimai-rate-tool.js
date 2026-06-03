#!/usr/bin/env node

const fs = require("node:fs/promises");
const path = require("node:path");

const API_BASE = "https://www.diving-fish.com/api/maimaidxprober";
const DEFAULT_CACHE = path.resolve(process.cwd(), "music_data.json");

const HELP = `maimai-rate-tool

Usage:
  maimai-rate-tool music [--cache ./music_data.json]
  maimai-rate-tool match --query <title> [--type SD|DX] [--diff master] [--cache ./music_data.json]
  maimai-rate-tool dx-score --judgements <json>
  maimai-rate-tool records [--top 10]
  maimai-rate-tool upload-record --title <title> --type <SD|DX> --diff <diff> --achievements <value> --dx-score <value> [--fc <fc>] [--fs <fs>]
  maimai-rate-tool upload-json <records.json>

Auth:
  Set MAIMAI_IMPORT_TOKEN for records/upload commands.
`;

function parseArgs(argv) {
  const positional = [];
  const options = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!arg.startsWith("--")) {
      positional.push(arg);
      continue;
    }
    const eq = arg.indexOf("=");
    if (eq !== -1) {
      options[arg.slice(2, eq)] = arg.slice(eq + 1);
      continue;
    }
    const key = arg.slice(2);
    const next = argv[i + 1];
    if (next == null || next.startsWith("--")) {
      options[key] = true;
    } else {
      options[key] = next;
      i++;
    }
  }
  return { positional, options };
}

function parseDiff(value) {
  const raw = String(value ?? "").trim().toLowerCase().replace(/\s+/g, "");
  const map = {
    "0": 0,
    bas: 0,
    basic: 0,
    "1": 1,
    adv: 1,
    advanced: 1,
    "2": 2,
    exp: 2,
    expert: 2,
    "3": 3,
    mas: 3,
    master: 3,
    "4": 4,
    remas: 4,
    remaster: 4,
    "re:master": 4,
    remastered: 4
  };
  if (!(raw in map)) {
    throw new Error(`Invalid diff "${value}". Use basic/advanced/expert/master/remaster or 0-4.`);
  }
  return map[raw];
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[「」『』"'`.,:;!?！？・~〜\-－_()[\]{}]/g, "");
}

function bigrams(value) {
  const s = normalizeText(value);
  if (s.length <= 1) return s ? [s] : [];
  const result = [];
  for (let i = 0; i < s.length - 1; i++) result.push(s.slice(i, i + 2));
  return result;
}

function similarity(a, b) {
  const A = bigrams(a);
  const B = new Set(bigrams(b));
  if (A.length === 0) return 0;
  return A.filter((item) => B.has(item)).length / A.length;
}

function getToken() {
  const token = process.env.MAIMAI_IMPORT_TOKEN;
  if (!token) throw new Error("Missing MAIMAI_IMPORT_TOKEN.");
  return token;
}

async function requestJson(pathname, { method = "GET", body } = {}) {
  const headers = { "Import-Token": getToken() };
  let payload;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const resp = await fetch(`${API_BASE}${pathname}`, { method, headers, body: payload });
  const text = await resp.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text };
    }
  }
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${data.message || data.status || resp.statusText}`);
  }
  return data;
}

async function fetchMusicData(cachePath) {
  try {
    const raw = await fs.readFile(cachePath, "utf8");
    return JSON.parse(raw);
  } catch {}

  const resp = await fetch(`${API_BASE}/music_data`);
  if (!resp.ok) throw new Error(`music_data HTTP ${resp.status}`);
  const data = await resp.json();
  await fs.mkdir(path.dirname(cachePath), { recursive: true });
  await fs.writeFile(cachePath, JSON.stringify(data, null, 2));
  return data;
}

function matchMusic(data, query, { type, diff }) {
  const diffIndex = diff == null ? null : parseDiff(diff);
  const normalizedType = type ? String(type).toUpperCase() : null;
  return data
    .filter((music) => !normalizedType || music.type === normalizedType)
    .map((music) => {
      const score = Math.max(
        similarity(query, music.title),
        normalizeText(music.title).includes(normalizeText(query)) ? 1 : 0
      );
      return {
        id: music.id,
        title: music.title,
        type: music.type,
        artist: music.basic_info?.artist,
        version: music.basic_info?.from,
        score,
        level_index: diffIndex,
        level: diffIndex == null ? music.level : music.level[diffIndex],
        ds: diffIndex == null ? music.ds : music.ds[diffIndex],
        cid: diffIndex == null ? undefined : music.cids[diffIndex],
        all_levels: music.level,
        all_ds: music.ds
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

function normalizeRecord(record) {
  const normalized = {
    title: String(record.title ?? "").trim(),
    type: String(record.type ?? "").trim().toUpperCase(),
    level_index: Number.isInteger(record.level_index) ? record.level_index : parseDiff(record.level_index ?? record.diff),
    achievements: Number(record.achievements),
    dxScore: Number(record.dxScore ?? record.dx_score ?? record["dx-score"] ?? 0),
    fc: String(record.fc ?? ""),
    fs: String(record.fs ?? "")
  };
  if (!normalized.title) throw new Error("Record is missing title.");
  if (normalized.type !== "SD" && normalized.type !== "DX") throw new Error("Record type must be SD or DX.");
  if (!Number.isFinite(normalized.achievements)) throw new Error("Record achievements must be numeric.");
  if (!Number.isFinite(normalized.dxScore)) throw new Error("Record dxScore must be numeric.");
  normalized.dxScore = Math.trunc(normalized.dxScore);
  return normalized;
}

function recordFromOptions(options) {
  return normalizeRecord({
    title: options.title,
    type: options.type,
    diff: options.diff,
    level_index: options["level-index"],
    achievements: options.achievements,
    dxScore: options["dx-score"] ?? options.dxScore,
    fc: options.fc,
    fs: options.fs
  });
}

function calculateDxScore(judgements) {
  const rows = Array.isArray(judgements) ? judgements : Object.values(judgements);
  let criticalPerfect = 0;
  let perfect = 0;
  let great = 0;
  let good = 0;
  let miss = 0;
  let total = 0;

  for (const row of rows) {
    if (!Array.isArray(row) || row.length < 5) {
      throw new Error("Each judgement row must be [criticalPerfect, perfect, great, good, miss].");
    }
    criticalPerfect += Number(row[0]);
    perfect += Number(row[1]);
    great += Number(row[2]);
    good += Number(row[3]);
    miss += Number(row[4]);
    total += row.slice(0, 5).reduce((sum, value) => sum + Number(value), 0);
  }

  return {
    criticalPerfect,
    perfect,
    great,
    good,
    miss,
    total,
    maxDxScore: total * 3,
    dxScore: criticalPerfect * 3 + perfect * 2 + great
  };
}

function summarizeRecords(data, topN) {
  const records = data.records || [];
  const byType = {};
  const byDiff = {};
  for (const record of records) {
    byType[record.type] = (byType[record.type] || 0) + 1;
    const diff = record.level_label || String(record.level_index);
    byDiff[diff] = (byDiff[diff] || 0) + 1;
  }
  const top = [...records]
    .sort((a, b) => (b.ra || 0) - (a.ra || 0))
    .slice(0, topN)
    .map((record) => ({
      title: record.title,
      type: record.type,
      level: record.level_label,
      achievements: record.achievements,
      dxScore: record.dxScore,
      ra: record.ra,
      fc: record.fc,
      fs: record.fs
    }));
  return {
    profile: {
      username: data.username,
      nickname: data.nickname,
      rating: data.rating,
      additional_rating: data.additional_rating,
      plate: data.plate
    },
    count: records.length,
    byType,
    byDiff,
    top
  };
}

async function loadRecords(file) {
  const raw = await fs.readFile(file, "utf8");
  const parsed = JSON.parse(raw);
  const records = Array.isArray(parsed) ? parsed : parsed.records;
  if (!Array.isArray(records)) throw new Error("JSON must be an array, or an object with a records array.");
  return records.map(normalizeRecord);
}

async function main() {
  const { positional, options } = parseArgs(process.argv.slice(2));
  const command = positional[0];
  if (!command || command === "help" || options.help) {
    process.stdout.write(HELP);
    return;
  }

  const cache = path.resolve(options.cache || DEFAULT_CACHE);

  if (command === "music") {
    const data = await fetchMusicData(cache);
    console.log(JSON.stringify({ cache, count: data.length }, null, 2));
    return;
  }

  if (command === "match") {
    if (!options.query) throw new Error("Missing --query.");
    const data = await fetchMusicData(cache);
    console.log(JSON.stringify(matchMusic(data, options.query, { type: options.type, diff: options.diff }), null, 2));
    return;
  }

  if (command === "dx-score") {
    if (!options.judgements) throw new Error("Missing --judgements JSON.");
    console.log(JSON.stringify(calculateDxScore(JSON.parse(options.judgements)), null, 2));
    return;
  }

  if (command === "records") {
    const topN = Number(options.top ?? 10);
    if (!Number.isInteger(topN) || topN < 0) throw new Error("--top must be a non-negative integer.");
    console.log(JSON.stringify(summarizeRecords(await requestJson("/player/records"), topN), null, 2));
    return;
  }

  if (command === "upload-record") {
    const record = recordFromOptions(options);
    const data = await requestJson("/player/update_records", { method: "POST", body: [record] });
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  if (command === "upload-json") {
    const file = positional[1];
    if (!file) throw new Error("Missing records JSON file.");
    const data = await requestJson("/player/update_records", { method: "POST", body: await loadRecords(file) });
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  throw new Error(`Unknown command "${command}".`);
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exitCode = 1;
});
