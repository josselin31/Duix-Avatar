import { get } from "@vercel/blob";
import { NextResponse } from "next/server";
import { getJobRecord } from "@/lib/job-store";

export const dynamic = "force-dynamic";

function blobAccessMode() {
  return process.env.BLOB_OBJECT_ACCESS === "public" ? "public" : "private";
}

function parseRangeHeader(rangeHeader, totalLength) {
  const header = String(rangeHeader || "").trim();
  const match = /^bytes=(\d*)-(\d*)$/i.exec(header);
  if (!match) return null;

  const rawStart = match[1];
  const rawEnd = match[2];
  if (!rawStart && !rawEnd) return null;

  let start;
  let end;

  if (!rawStart) {
    const suffixLength = Number(rawEnd);
    if (!Number.isFinite(suffixLength) || suffixLength <= 0) return "invalid";
    start = Math.max(totalLength - suffixLength, 0);
    end = totalLength - 1;
  } else {
    start = Number(rawStart);
    if (!Number.isFinite(start) || start < 0 || start >= totalLength) return "invalid";

    if (!rawEnd) {
      end = totalLength - 1;
    } else {
      end = Number(rawEnd);
      if (!Number.isFinite(end)) return "invalid";
      end = Math.min(end, totalLength - 1);
    }
  }

  if (end < start) return "invalid";
  return { start, end };
}

export async function GET(request, { params }) {
  try {
    const id = params?.id;
    if (!id) {
      return NextResponse.json({ error: "Missing job id." }, { status: 400 });
    }

    const { searchParams } = new URL(request.url);
    const type = searchParams.get("type");
    if (!type || !["source", "video"].includes(type)) {
      return NextResponse.json({ error: "Invalid asset type." }, { status: 400 });
    }

    const job = await getJobRecord(id);
    if (!job) {
      return NextResponse.json({ error: "Job not found." }, { status: 404 });
    }

    const pathname = type === "source" ? job.sourceMarkdownPath : job.outputVideoPath;
    if (!pathname) {
      return NextResponse.json({ error: "Asset not available." }, { status: 404 });
    }

    const blob = await get(pathname, {
      access: blobAccessMode(),
      token: process.env.BLOB_READ_WRITE_TOKEN
    });
    if (!blob || !blob.stream) {
      return NextResponse.json({ error: "Asset stream unavailable." }, { status: 404 });
    }

    const bytes = new Uint8Array(await new Response(blob.stream).arrayBuffer());
    const totalLength = bytes.byteLength;
    const requestedRange = parseRangeHeader(request.headers.get("range"), totalLength);

    if (requestedRange === "invalid") {
      return new Response(null, {
        status: 416,
        headers: {
          "content-range": `bytes */${totalLength}`,
          "accept-ranges": "bytes",
          "cache-control": "private, max-age=120"
        }
      });
    }

    const headers = new Headers();
    headers.set("content-type", type === "video" ? "video/mp4" : "text/markdown; charset=utf-8");
    headers.set(
      "content-disposition",
      type === "video" ? `inline; filename=\"${id}.mp4\"` : `inline; filename=\"${id}.md\"`
    );
    headers.set("accept-ranges", "bytes");
    headers.set("cache-control", "private, max-age=120");

    if (requestedRange && type === "video") {
      const { start, end } = requestedRange;
      const chunk = bytes.slice(start, end + 1);
      headers.set("content-range", `bytes ${start}-${end}/${totalLength}`);
      headers.set("content-length", String(chunk.byteLength));
      return new Response(chunk, { status: 206, headers });
    }

    headers.set("content-length", String(totalLength));
    return new Response(bytes, { status: 200, headers });
  } catch (error) {
    return NextResponse.json(
      { error: error.message || "Unable to retrieve asset." },
      { status: 500 }
    );
  }
}
