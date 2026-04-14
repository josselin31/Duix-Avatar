export const RETENTION_HOURS = Number(process.env.JOBS_RETENTION_HOURS || 24);

export const OPENAI_VIDEO_MODEL = process.env.OPENAI_VIDEO_MODEL || "sora-2";
export const OPENAI_VIDEO_SECONDS = process.env.OPENAI_VIDEO_SECONDS || "12";
export const OPENAI_VIDEO_SIZE = process.env.OPENAI_VIDEO_SIZE || "720x1280";

export function getRequiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

export function nowIso() {
  return new Date().toISOString();
}

export function isExpired(isoDate, retentionHours = RETENTION_HOURS) {
  if (!isoDate) return true;
  const createdAtMs = new Date(isoDate).getTime();
  if (Number.isNaN(createdAtMs)) return true;
  const ageMs = Date.now() - createdAtMs;
  return ageMs > retentionHours * 60 * 60 * 1000;
}
