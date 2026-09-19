import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json({
    access_token: "demo-jwt-token-technician-preview",
    token_type: "bearer",
    expires_in: 3600,
    user: {
      email: "tech@industrial.test",
      tenant_id: "demo",
      site_ids: ["SITE-A"],
      roles: ["technician"],
    },
  });
}
