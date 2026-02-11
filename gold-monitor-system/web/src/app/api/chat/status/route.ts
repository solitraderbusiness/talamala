/**
 * Next.js Route Handler for GET /api/chat/status
 *
 * Simple proxy to the FastAPI backend chat status endpoint.
 */

export const dynamic = "force-dynamic";

const BACKEND = process.env.INTERNAL_API_URL || "http://api:8000";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/api/chat/status`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    console.error("[chat-status-proxy] Backend fetch failed:", err);
    return Response.json(
      { enabled: false, welcome_message: "" },
      { status: 200 }
    );
  }
}
