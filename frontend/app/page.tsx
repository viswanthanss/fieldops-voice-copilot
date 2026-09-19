"use client";

import React, { useState } from "react";
import { LiveKitVoiceSession } from "@/components/voice/LiveKitVoiceSession";
import { EvidencePanel } from "@/components/voice/EvidencePanel";
import { loginAndGetToken, initializeVoiceSession } from "@/lib/api";
import { TurnAttribution, SessionResponse } from "@/types";
import { ShieldCheck, Wrench, Radio, Cpu, Volume2, Info } from "lucide-react";

export default function Home() {
  const [sessionData, setSessionData] = useState<SessionResponse | null>(null);
  const [attribution, setAttribution] = useState<TurnAttribution | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedAsset, setSelectedAsset] = useState("CP-204");

  const startVoiceSession = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      // 1. Authenticate technician with control plane
      const token = await loginAndGetToken();
      // 2. Derive server-side authorization context and obtain LiveKit session token
      const session = await initializeVoiceSession(token, selectedAsset);
      setSessionData(session);
    } catch (err: any) {
      console.warn("Session activation note:", err);
      // Safe fallback: activates demo preview session
      setSessionData({
        session_id: `demo-sess-${Date.now()}`,
        livekit_token: "demo-livekit-token",
        livekit_url: "",
        auth_context: {
          tenant_id: "demo",
          site_ids: ["SITE-A"],
          asset_ids: [selectedAsset],
          roles: ["technician"],
          user_id: "usr-tech-01",
        },
        expires_at: new Date(Date.now() + 3600 * 1000).toISOString(),
        is_demo: true,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisconnect = () => {
    setSessionData(null);
  };

  return (
    <main className="flex flex-col h-screen max-w-7xl mx-auto p-4 space-y-4">
      {/* Top Header */}
      <header className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
            <Radio className="w-5 h-5 text-slate-950" />
          </div>
          <div>
            <h1 className="text-base font-bold text-slate-100 flex items-center space-x-2">
              <span>FIELDOPS VOICE COPILOT</span>
              <span className="text-[10px] px-2 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-full font-mono">
                YC Fall 2026 × Moss Sprint
              </span>
            </h1>
            <p className="text-xs text-slate-400">
              Evidence-Gated Realtime Voice AI with In-Process Embedded Moss Runtime
            </p>
          </div>
        </div>

        {/* System Badges */}
        <div className="flex items-center space-x-2 text-xs">
          <span className="flex items-center px-2.5 py-1 bg-slate-900 border border-slate-800 rounded-lg text-slate-300 font-mono">
            <Cpu className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
            Moss Embedded &lt;10ms
          </span>
          <span className="flex items-center px-2.5 py-1 bg-slate-900 border border-slate-800 rounded-lg text-slate-300 font-mono">
            <ShieldCheck className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
            Evidence Gate Active
          </span>
        </div>
      </header>

      {/* Equipment Maintenance Scope Banner */}
      <div className="flex items-center justify-between p-3 bg-slate-900/60 border border-slate-800 rounded-xl text-xs">
        <div className="flex items-center space-x-4">
          <div className="flex items-center text-slate-300">
            <Wrench className="w-4 h-4 mr-1.5 text-slate-400" />
            <span className="text-slate-400 mr-1">Active Asset:</span>
            <span className="font-semibold text-slate-200">{selectedAsset}</span>
            <span className="ml-1.5 text-[11px] text-slate-400">(CP-200 Reciprocating Compressor)</span>
          </div>

          <div className="flex items-center space-x-2 text-[11px] text-slate-400 border-l border-slate-800 pl-4">
            <span>Tenant: <strong className="text-slate-300">demo</strong></span>
            <span>•</span>
            <span>Site: <strong className="text-slate-300">SITE-A</strong></span>
            <span>•</span>
            <span>Role: <strong className="text-slate-300">technician</strong></span>
          </div>
        </div>

        {!sessionData && (
          <div className="flex items-center space-x-2">
            <button
              onClick={startVoiceSession}
              disabled={isLoading}
              className="px-4 py-1.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-semibold rounded-lg shadow-md transition-all disabled:opacity-50 text-xs flex items-center space-x-1.5 cursor-pointer"
            >
              <Volume2 className="w-4 h-4" />
              <span>{isLoading ? "Authenticating..." : "Start Voice Session"}</span>
            </button>
          </div>
        )}
      </div>

      {/* Controlled Public Demo Notice (Non-blocking) */}
      {sessionData?.is_demo && (
        <div className="px-3.5 py-2 bg-slate-900/90 border border-amber-500/30 rounded-xl text-xs text-slate-300 flex items-center justify-between shadow-sm">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-amber-400"></span>
            <span>
              <strong>Public Demo Mode:</strong> Live voice service is not configured for this public preview. Interactive Evidence Gate &amp; Grounding scenarios are enabled below.
            </span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 bg-amber-500/10 text-amber-300 border border-amber-500/20 rounded">
            DEMO PREVIEW
          </span>
        </div>
      )}

      {errorMessage && (
        <div className="p-3 bg-rose-950/50 border border-rose-800 text-rose-300 rounded-xl text-xs flex items-center justify-between">
          <span>{errorMessage}</span>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-slate-400 hover:text-slate-200 text-sm font-bold"
          >
            ×
          </button>
        </div>
      )}

      {/* Main Realtime Workspace (2-Column Grid) */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4 min-h-0">
        {/* Left: Voice Session & Transcript */}
        <div className="h-full flex flex-col">
          {sessionData ? (
            <LiveKitVoiceSession
              token={sessionData.livekit_token}
              serverUrl={sessionData.livekit_url}
              activeAsset={selectedAsset}
              onAttributionUpdate={setAttribution}
              onDisconnect={handleDisconnect}
            />
          ) : (
            <div className="h-full flex flex-col items-center justify-center p-8 bg-slate-900/40 rounded-xl border border-dashed border-slate-800 text-center space-y-4">
              <div className="w-16 h-16 rounded-full bg-slate-800/80 flex items-center justify-center text-slate-400">
                <Radio className="w-8 h-8" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-200">Technician Radio Ready</h3>
                <p className="text-xs text-slate-400 max-w-sm mt-1">
                  Click "Start Voice Session" to connect to the LiveKit voice server with server-derived cryptographic authorization.
                </p>
              </div>
              <button
                onClick={startVoiceSession}
                disabled={isLoading}
                className="px-5 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold rounded-lg shadow-lg text-xs cursor-pointer"
              >
                {isLoading ? "Connecting..." : "Connect Hands-Free Radio"}
              </button>
            </div>
          )}
        </div>

        {/* Right: Realtime Evidence & Grounding Inspector */}
        <div className="h-full flex flex-col">
          <EvidencePanel attribution={attribution} activeAsset={selectedAsset} />
        </div>
      </div>
    </main>
  );
}
