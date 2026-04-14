import { NextResponse } from "next/server";
import { getJobRecord } from "@/lib/job-store";
import { refreshJobStatus } from "@/lib/job-runtime";

export const dynamic = "force-dynamic";

function toClientJob(job) {
  return {
    ...job,
    sourceMarkdownUrl: `/api/jobs/${job.id}/asset?type=source`,
    outputVideoUrl: job.status === "completed" ? `/api/jobs/${job.id}/asset?type=video` : ""
  };
}

export async function GET(request, { params }) {
  try {
    const { searchParams } = new URL(request.url);
    const shouldRefresh = searchParams.get("refresh") === "1";
    const id = params?.id;
    if (!id) {
      return NextResponse.json({ error: "Missing job id." }, { status: 400 });
    }

    const job = await getJobRecord(id);
    if (!job) {
      return NextResponse.json({ error: "Job not found." }, { status: 404 });
    }

    const responseJob = shouldRefresh ? await refreshJobStatus(job) : job;
    return NextResponse.json({ job: toClientJob(responseJob) });
  } catch (error) {
    return NextResponse.json({ error: error.message || "Unable to retrieve job." }, { status: 500 });
  }
}
