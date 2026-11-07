// Generates the voiceover with ElevenLabs, one clip per scene, and writes out/voice/manifest.json
// with each clip's length so the recorder can pace scenes to the narration.
// Needs in ../.env:  ELEVENLABS_API_KEY=...   (optional: ELEVENLABS_VOICE_ID=..., ELEVENLABS_MODEL=...)
// Run:  npm run voice
import fs from "node:fs";
import path from "node:path";
import { LINES } from "./script.mjs";

const env = {};
const envPath = path.resolve("..", ".env");
if (fs.existsSync(envPath)) for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
  const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/); if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
}
const KEY = process.env.ELEVENLABS_API_KEY || env.ELEVENLABS_API_KEY;
if (!KEY) { console.error("No ELEVENLABS_API_KEY in .env"); process.exit(1); }
const VOICE = process.env.ELEVENLABS_VOICE_ID || env.ELEVENLABS_VOICE_ID || "21m00Tcm4TlvDq8ikWAM";
const MODEL = process.env.ELEVENLABS_MODEL || env.ELEVENLABS_MODEL || "eleven_multilingual_v2";
const OUT = path.resolve("out", "voice");
fs.mkdirSync(OUT, { recursive: true });

async function listVoices() {
  const r = await fetch("https://api.elevenlabs.io/v1/voices", { headers: { "xi-api-key": KEY } });
  if (!r.ok) return console.error("Could not list voices:", r.status, (await r.text()).slice(0, 200));
  const j = await r.json();
  console.error("Voices on your account (set ELEVENLABS_VOICE_ID in .env to one of these):");
  for (const v of j.voices || []) console.error(`  ${v.voice_id}  ${v.name}`);
}

const manifest = { voice: VOICE, model: MODEL, clips: [] };
for (const [i, text] of LINES.entries()) {
  const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${VOICE}/with-timestamps?output_format=mp3_44100_128`, {
    method: "POST",
    headers: { "xi-api-key": KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ text, model_id: MODEL, voice_settings: { stability: 0.5, similarity_boost: 0.75 } }),
  });
  if (!r.ok) {
    console.error(`Clip ${i} failed: ${r.status} ${(await r.text()).slice(0, 300)}`);
    if (r.status === 404 || r.status === 400) await listVoices();
    process.exit(1);
  }
  const j = await r.json();
  const file = `line_${i}.mp3`;
  fs.writeFileSync(path.join(OUT, file), Buffer.from(j.audio_base64, "base64"));
  const ends = j.alignment?.character_end_times_seconds || [];
  const seconds = ends.length ? ends[ends.length - 1] : null;
  manifest.clips.push({ i, file, seconds, text });
  console.log(`line ${i}: ${seconds ? seconds.toFixed(1) + " s" : "length unknown"}  ${text.slice(0, 60)}…`);
}
fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 1));
console.log("saved", OUT);
