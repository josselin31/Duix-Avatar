import { NextResponse } from "next/server";
import {
  buildSourceMarkdown,
  createInitialJobRecord,
  listJobRecords,
  saveSourceMarkdown
} from "@/lib/job-store";
import { createVideoJob } from "@/lib/openai-video";
import { refreshJobStatus, toVideoPrompt } from "@/lib/job-runtime";

export const dynamic = "force-dynamic";

function normalizeText(value) {
  return String(value || "")
    .replace(/\r\n/g, "\n")
    .trim();
}

function toClientJob(job) {
  return {
    ...job,
    sourceMarkdownUrl: `/api/jobs/${job.id}/asset?type=source`,
    outputVideoUrl: job.status === "completed" ? `/api/jobs/${job.id}/asset?type=video` : ""
  };
}

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const shouldRefresh = searchParams.get("refresh") === "1";
    const jobs = await listJobRecords();
    if (!shouldRefresh) {
      return NextResponse.json({ jobs: jobs.map(toClientJob) });
    }

    const refreshed = [];
    for (const job of jobs) {
      if (job.status === "queued" || job.status === "in_progress" || (job.status === "completed" && !job.outputVideoUrl)) {
        refreshed.push(await refreshJobStatus(job));
      } else {
        refreshed.push(job);
      }
    }

    refreshed.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    return NextResponse.json({ jobs: refreshed.map(toClientJob) });
  } catch (error) {
    return NextResponse.json({ error: error.message || "Unable to list jobs." }, { status: 500 });
  }
}

export async function POST(request) {
  try {
    const payload = await request.json();
    const text = normalizeText(payload?.text);

    if (!text || text.length < 1) {
      return NextResponse.json({ error: "Le texte ne peut pas être vide." }, { status: 400 });
    }
    if (text.length > 4000) {
      return NextResponse.json({ error: "Le texte est trop long (max 4000 caractères)." }, { status: 400 });
    }

    const id = crypto.randomUUID().replace(/-/g, "");
    const markdown = buildSourceMarkdown(text);
    const sourceBlob = await saveSourceMarkdown(id, markdown);
    const videoPrompt = await toVideoPrompt(text);
    const videoJob = await createVideoJob(videoPrompt);

    const job = await createInitialJobRecord({
      id,
      text,
      sourceMarkdownUrl: sourceBlob.url,
      openaiVideoId: videoJob.id,
      status: videoJob.status || "queued"
    });

    return NextResponse.json({ job: toClientJob(job) }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error.message || "Unable to create job." }, { status: 500 });
  }
}
