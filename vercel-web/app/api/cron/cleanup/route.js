import { NextResponse } from "next/server";
import { deleteJobAssets, listJobRecords } from "@/lib/job-store";
import { isExpired } from "@/lib/config";

export const dynamic = "force-dynamic";

function isAuthorized(request) {
  const secret = process.env.CRON_SECRET;
  if (!secret) return true;
  const bearer = request.headers.get("authorization");
  const direct = request.headers.get("x-cron-secret");
  return bearer === `Bearer ${secret}` || direct === secret;
}

export async function GET(request) {
  try {
    if (!isAuthorized(request)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const jobs = await listJobRecords({ refreshExpired: true });
    let removedJobs = 0;
    let removedFiles = 0;

    for (const job of jobs) {
      if (!isExpired(job.createdAt)) continue;
      removedFiles += await deleteJobAssets(job.id);
      removedJobs += 1;
    }

    return NextResponse.json({
      ok: true,
      removedJobs,
      removedFiles
    });
  } catch (error) {
    return NextResponse.json({ error: error.message || "Cleanup failed." }, { status: 500 });
  }
}
