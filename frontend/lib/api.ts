import { SessionResponse } from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function loginAndGetToken(username = "tech@industrial.test", password = "SafePassword123!"): Promise<string> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);

  const res = await fetch(`${API_BASE_URL}/api/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formData.toString(),
  });

  if (!res.ok) {
    throw new Error(`Auth failed: ${res.statusText}`);
  }

  const data = await res.json();
  return data.access_token;
}

export async function initializeVoiceSession(jwtToken: string, assetId = "CP-204"): Promise<SessionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/session/initialize`, {
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
}
