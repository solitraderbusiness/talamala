/**
 * Next.js Route Handler for POST /api/chat
 *
 * Proxies the chat request to the FastAPI backend and streams the SSE
 * response back to the client.  Next.js rewrites() do NOT properly
 * handle long-lived SSE streams — this route handler gives us full
 * control over the streaming pipe.
 */

import { NextRequest } from "next/server";

// Ensure this route is never statically cached
export const dynamic = "force-dynamic";

const BACKEND = process.env.INTERNAL_API_URL || "http://api:8000";

export async function POST(request: NextRequest) {
  const body = await request.text();

  // Forward the client IP so the backend rate-limiter works
  const forwarded =
    request.headers.get("x-forwarded-for") ||
    request.headers.get("x-real-ip") ||
    "unknown";

  let backendRes: Response;
  try {
    backendRes = await fetch(`${BACKEND}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Forwarded-For": forwarded,
      },
      body,
      // Disable Next.js fetch caching and ensure true streaming
      cache: "no-store",
    });
  } catch (err) {
    console.error("[chat-proxy] Backend fetch failed:", err);
    return Response.json(
      { error: "backend_unavailable", message: "سرویس در دسترس نیست." },
      { status: 502 }
    );
  }

  // If backend returned JSON (error responses), forward as-is
  const ct = backendRes.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    const data = await backendRes.json();
    return Response.json(data, { status: backendRes.status });
  }

  // Stream the SSE body back to the client
  if (!backendRes.body) {
    return Response.json(
      { error: "empty_body", message: "پاسخی دریافت نشد." },
      { status: 502 }
    );
  }

  const sessionId = backendRes.headers.get("X-Chat-Session-Id");

  const responseHeaders: Record<string, string> = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  };
  if (sessionId) {
    responseHeaders["X-Chat-Session-Id"] = sessionId;
  }

  return new Response(backendRes.body, {
    status: 200,
    headers: responseHeaders,
  });
}
