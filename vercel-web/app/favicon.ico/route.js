import { NextResponse } from "next/server";

export function GET(request) {
  const target = new URL("/icon.svg", request.url);
  return NextResponse.redirect(target, 307);
}
