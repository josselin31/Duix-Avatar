import { nowIso } from "./config";
import { downloadVideoContent, retrieveVideoJob } from "./openai-video";
import { saveJobRecord, saveOutputVideo } from "./job-store";

export function toVideoPrompt(text) {
  return [
    "Create a vertical short video for TikTok/Reels, mobile-first and clean Apple-like visual style.",
    "Keep pacing dynamic and make on-screen information easy to read on iPhone.",
    "",
    `Script context:\n${text}`
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
