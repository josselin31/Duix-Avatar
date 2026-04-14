import { getRequiredEnv, OPENAI_VIDEO_MODEL, OPENAI_VIDEO_SECONDS, OPENAI_VIDEO_SIZE } from "./config";

const OPENAI_API_BASE = "https://api.openai.com/v1";

async function openaiRequest(path, { method = "GET", body, contentType = "application/json" } = {}) {
  const apiKey = getRequiredEnv("OPENAI_API_KEY");
  const res = await fetch(`${OPENAI_API_BASE}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      ...(body ? { "Content-Type": contentType } : {})
    },
    body: body ? JSON.stringify(body) : undefined
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`OpenAI error ${res.status}: ${text}`);
  }

  return res;
}

export async function createVideoJob(prompt) {
  const res = await openaiRequest("/videos", {
    method: "POST",
    body: {
      model: OPENAI_VIDEO_MODEL,
      prompt,
      seconds: OPENAI_VIDEO_SECONDS,
      size: OPENAI_VIDEO_SIZE
    }
  });
  return res.json();
}

export async function retrieveVideoJob(videoId) {
  const res = await openaiRequest(`/videos/${videoId}`);
  return res.json();
}

export async function downloadVideoContent(videoId) {
  const res = await openaiRequest(`/videos/${videoId}/content?variant=video`);
  const bytes = await res.arrayBuffer();
  return Buffer.from(bytes);
}
