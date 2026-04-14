import { nowIso } from "./config";
import { downloadVideoContent, retrieveVideoJob } from "./openai-video";
import { saveJobRecord, saveOutputVideo } from "./job-store";
import path from "path";
import { readFile } from "fs/promises";

const FALLBACK_PERFECT_SORA_BASE = `
## Prompt Analysis Summary
### What Makes Sora 2 Prompts Go Viral?
1. Novelty factor with model capabilities.
2. Relatability with everyday contexts.
3. Humor or surprise contrast.
4. Technical impressiveness with clear action.
5. Practical value for content creators.

### Emerging Prompt Patterns
1. Audio-first prompts with explicit ambience/dialogue.
2. Style shorthand with recognizable aesthetics.
3. Sequential specifications with temporal beats.
4. Camera transitions and editorial control.

## Tips for Creating Viral Sora 2 Prompts
1. Define hook in first 1-2 seconds.
2. Keep scene pacing fast with explicit transitions.
3. Make mobile readability a priority.
4. Request realistic camera movement and natural lighting.
5. End with a strong payoff/CTA visual beat.

## Advanced Techniques
### Narrative with Cuts
Use explicit [CUT TO] transitions, camera angle shifts and short action blocks.

### Voiceover Recording Hack
Specify clean voice context and concise line delivery cues.
`.trim();

let cachedPerfectSoraBase = null;

function normalizeBlock(value) {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function extractSection(markdown, startHeading, endHeading) {
  const start = markdown.indexOf(startHeading);
  if (start < 0) return "";
  const afterStart = markdown.slice(start);
  if (!endHeading) return normalizeBlock(afterStart);
  const end = afterStart.indexOf(endHeading);
  return normalizeBlock(end >= 0 ? afterStart.slice(0, end) : afterStart);
}

async function loadPerfectSoraBase() {
  if (cachedPerfectSoraBase) {
    return cachedPerfectSoraBase;
  }

  const candidates = [
    path.join(process.cwd(), "PerfectPromptSora.md"),
    path.join(process.cwd(), "..", "PerfectPromptSora.md")
  ];

  for (const candidate of candidates) {
    try {
      const raw = await readFile(candidate, "utf8");
      const summary = extractSection(raw, "## Prompt Analysis Summary", "## Absurd & Viral Humor");
      const cuts = extractSection(raw, "### Narrative with Cuts", "### Voiceover Recording Hack");
      const voiceover = extractSection(raw, "### Voiceover Recording Hack", "### Solarpunk Group Scene");
      const merged = normalizeBlock([summary, cuts, voiceover].filter(Boolean).join("\n\n"));
      if (merged) {
        cachedPerfectSoraBase = merged;
        return cachedPerfectSoraBase;
      }
    } catch {
      // Continue to next candidate path.
    }
  }

  cachedPerfectSoraBase = FALLBACK_PERFECT_SORA_BASE;
  return cachedPerfectSoraBase;
}

export async function toVideoPrompt(text) {
  const base = await loadPerfectSoraBase();
  return [
    "Use the following Sora prompt foundation extracted from PerfectPromptSora.md:",
    base,
    "",
    "Now generate one single, production-ready prompt for Sora-2 using this creator brief.",
    "Hard requirements:",
    "- Vertical 9:16 format, short-form social style, max 12 seconds.",
    "- Strong 0-2s hook, rapid pacing, clear scene transitions.",
    "- Realistic visuals with phone-native readability and dynamic camera movement.",
    "- Include audio cues (voiceover/ambience) when relevant.",
    "- Keep output as a direct video-generation prompt (no markdown headings).",
    "",
    "Creator brief:",
    text
  ].join("\n");
}

export async function refreshJobStatus(job) {
  if (!job?.openaiVideoId) return job;
  if (job.status === "failed") return job;
  if (job.status === "completed" && job.outputVideoUrl) return job;

  const latest = await retrieveVideoJob(job.openaiVideoId);
  const status = latest.status || job.status;

  const updated = {
    ...job,
    status,
    updatedAt: nowIso(),
    errorMessage: latest.error?.message || job.errorMessage || ""
  };

  if (status === "completed" && !updated.outputVideoUrl) {
    const videoBuffer = await downloadVideoContent(job.openaiVideoId);
    const uploaded = await saveOutputVideo(job.id, videoBuffer);
    updated.outputVideoUrl = uploaded.url;
  }

  return saveJobRecord(updated);
}
