import { SessionResponse } from "@/types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "").trim().replace(/\/+$/, "");

export async function loginAndGetToken(
  username = "tech@industrial.test",
  password = "SafePassword123!"
): Promise<string> {
  const url = API_BASE_URL ? `${API_BASE_URL}/api/v1/auth/token` : "/api/v1/auth/token";

  try {
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData.toString(),
    });

    if (!res.ok) {
      throw new Error(`Auth failed: ${res.statusText}`);
    }

    const data = await res.json();
    return data.access_token || "demo-jwt-token-technician-preview";
  } catch (err: any) {
    console.warn("Live auth endpoint unavailable; activating demo session scope:", err.message);
    return "demo-jwt-token-technician-preview";
  }
}

export async function initializeVoiceSession(
  jwtToken: string,
  assetId = "CP-204"
): Promise<SessionResponse> {
  const url = API_BASE_URL ? `${API_BASE_URL}/api/v1/session/initialize` : "/api/v1/session/initialize";

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${jwtToken}`,
      },
      body: JSON.stringify({ asset_id: assetId }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Failed to initialize session");
    }

    return res.json();
  } catch (err: any) {
    console.warn("Live session initialization unavailable; falling back to demo session:", err.message);
    return {
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
    };
  }
}
