/**
 * Next.js Route Handler for GET /api/chat/history
 *
 * Proxies to the FastAPI backend to load chat messages for a session.
 */

import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.INTERNAL_API_URL || "http://api:8000";

export async function GET(request: NextRequest) {
  const sessionId = request.nextUrl.searchParams.get("session_id") || "";

  try {
    const res = await fetch(
      `${BACKEND}/api/chat/history?session_id=${encodeURIComponent(sessionId)}`,
      { cache: "no-store" }
    );
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    console.error("[chat-history-proxy] Backend fetch failed:", err);
    return Response.json({ messages: [] }, { status: 200 });
  }
}
