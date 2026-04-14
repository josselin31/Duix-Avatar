import { del, get, list, put } from "@vercel/blob";
import { isExpired, nowIso } from "./config";

function jobPrefix(id) {
  return `jobs/${id}`;
}

function jobJsonPath(id) {
  return `${jobPrefix(id)}/job.json`;
}

function sourceMdPath(id) {
  return `${jobPrefix(id)}/source.md`;
}

function outputVideoPath(id) {
  return `${jobPrefix(id)}/output.mp4`;
}

function blobAccessMode() {
  return process.env.BLOB_OBJECT_ACCESS === "public" ? "public" : "private";
}

async function listAllBlobs(prefix) {
  let cursor;
  const all = [];

  do {
    const page = await list({
      prefix,
      cursor
    });
    all.push(...(page.blobs || []));
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);

  return all;
}

async function readJsonBlob(pathname) {
  const blob = await get(pathname, {
    access: blobAccessMode(),
    token: process.env.BLOB_READ_WRITE_TOKEN
  });
  if (!blob || !blob.stream) {
    throw new Error("Unable to read blob JSON stream.");
  }
  const body = await new Response(blob.stream).text();
  return JSON.parse(body);
}

export function buildSourceMarkdown(text) {
  return [
    "# Video Prompt",
    "",
    `Created at: ${new Date().toISOString()}`,
    "",
    "## Input",
    "",
    text.trim()
  ].join("\n");
}

export async function saveSourceMarkdown(id, markdown) {
  return put(sourceMdPath(id), markdown, {
    access: blobAccessMode(),
    addRandomSuffix: false,
    contentType: "text/markdown; charset=utf-8"
  });
}

export async function saveJobRecord(job) {
  const saved = await put(jobJsonPath(job.id), JSON.stringify(job, null, 2), {
    access: blobAccessMode(),
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json; charset=utf-8"
  });
  return { ...job, jobJsonUrl: saved.url };
}

export async function createInitialJobRecord({ id, text, sourceMarkdownUrl, openaiVideoId, status }) {
  const createdAt = nowIso();
  return saveJobRecord({
    id,
    status: status || "queued",
    createdAt,
    updatedAt: createdAt,
    sourceText: text,
    previewText: `${text.slice(0, 140)}${text.length > 140 ? "..." : ""}`,
    sourceMarkdownUrl: sourceMarkdownUrl || "",
    sourceMarkdownPath: sourceMdPath(id),
    openaiVideoId,
    outputVideoPath: outputVideoPath(id),
    outputVideoUrl: "",
    errorMessage: ""
  });
}

export async function getJobRecord(id) {
  try {
    return await readJsonBlob(jobJsonPath(id));
  } catch {
    return null;
  }
}

export async function listJobRecords({ refreshExpired = false } = {}) {
  const blobs = await listAllBlobs("jobs/");
  const jobBlobs = blobs.filter((item) => item.pathname.endsWith("/job.json"));
  const jobs = [];

  for (const blob of jobBlobs) {
    try {
      const job = await readJsonBlob(blob.pathname);
      if (!refreshExpired && isExpired(job.createdAt)) {
        continue;
      }
      jobs.push(job);
    } catch {
      // Skip malformed records.
    }
  }

  jobs.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  return jobs;
}

export async function saveOutputVideo(id, videoBuffer) {
  return put(outputVideoPath(id), videoBuffer, {
    access: blobAccessMode(),
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "video/mp4"
  });
}

export async function deleteJobAssets(id) {
  const blobs = await listAllBlobs(`${jobPrefix(id)}/`);
  if (!blobs.length) return 0;
  await del(blobs.map((item) => item.url));
  return blobs.length;
}
