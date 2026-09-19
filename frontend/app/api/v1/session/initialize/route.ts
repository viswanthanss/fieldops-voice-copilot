import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const assetId = body.asset_id || "CP-204";

  return NextResponse.json({
    session_id: `demo-sess-${Date.now()}`,
    livekit_token: "demo-livekit-token-preview",
    livekit_url: "",
    auth_context: {
      tenant_id: "demo",
      site_ids: ["SITE-A"],
      asset_ids: [assetId],
      roles: ["technician"],
      user_id: "usr-tech-01",
    },
    expires_at: new Date(Date.now() + 3600 * 1000).toISOString(),
    is_demo: true,
  });
}
