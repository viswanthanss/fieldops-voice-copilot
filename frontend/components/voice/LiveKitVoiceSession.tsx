"use client";

import React, { useState, useEffect, useRef } from "react";
import { Room, RoomEvent, Track } from "livekit-client";
import { Mic, MicOff, Volume2, Radio, Activity, Sparkles, Info } from "lucide-react";
import { VoiceMessage, TurnAttribution } from "@/types";

interface LiveKitVoiceSessionProps {
  token: string;
  serverUrl: string;
  activeAsset: string;
  onAttributionUpdate: (attr: TurnAttribution) => void;
  onDisconnect: () => void;
}

const DEMO_SCENARIO_DATA: Record<
  number,
  { responseText: string; attribution: TurnAttribution }
> = {
  1: {
    responseText:
      "For error E17 on the CP-200 compressor, immediately check the discharge temperature sensor and oil cooler lines. Per service manual DOC-CP200-MAN Rev 2.1 Section 4.2, ensure discharge temp does not exceed 185°F to prevent high-temp thermal shutdown.",
    attribution: {
      turn_id: 1,
      retrieval_id: "ret-live-e17-cp204",
      evidence_gate_decision: "PASS",
      grounding_status: "PASS",
      retrieved_evidence: [
        {
          document_id: "DOC-CP200-MAN",
          document_type: "manual",
          revision: "2.1",
          model: "CP-200",
          section: "4.2 - High Temperature Diagnostics",
          score: 0.94,
          snippet:
            "Error E17 indicates high discharge temperature (>185°F). Inspect condenser coils, verify coolant level, and ensure lubricating oil flow meets OEM specifications.",
        },
        {
          document_id: "DOC-CP200-ERR",
          document_type: "error-code",
          revision: "1.0",
          model: "CP-200",
          section: "E17 Fault Isolation",
          score: 0.89,
          snippet:
            "E17: Discharge Temp Exceeded. Action: Allow 15 min cool-down, verify oil thermal bypass valve position, restart only after temperature drops below 160°F.",
        },
      ],
      latencies: {
        normalization_ms: 0.18,
        authorization_ms: 0.12,
        retrieval_ms: 7.4,
        evidence_gate_ms: 0.49,
        llm_generation_ms: 310.0,
        grounding_validation_ms: 42.0,
        total_ms: 360.19,
      },
      prompt_version: "v1.2.0",
    },
  },
  2: {
    responseText:
      "Safety Refusal: Active equipment authorization is restricted to CP-200 (Asset CP-204). Procedures for model CP-300 are blocked by the Evidence Gate to prevent equipment cross-contamination.",
    attribution: {
      turn_id: 2,
      retrieval_id: "ret-mismatch-cp300",
      evidence_gate_decision: "FAIL_EQUIPMENT_MISMATCH",
      grounding_status: "SKIPPED",
      retrieved_evidence: [],
      latencies: {
        normalization_ms: 0.15,
        authorization_ms: 0.11,
        retrieval_ms: 0.0,
        evidence_gate_ms: 0.42,
        total_ms: 0.68,
      },
      prompt_version: "v1.2.0",
    },
  },
  3: {
    responseText:
      "Diagnostic Refusal: Error code E99 was not found in the authorized OEM service documentation for model CP-200. Please escalate to tier-2 industrial compressor support.",
    attribution: {
      turn_id: 3,
      retrieval_id: "ret-no-evidence-e99",
      evidence_gate_decision: "FAIL_NO_EVIDENCE",
      grounding_status: "SKIPPED",
      retrieved_evidence: [],
      latencies: {
        normalization_ms: 0.17,
        authorization_ms: 0.10,
        retrieval_ms: 6.8,
        evidence_gate_ms: 0.38,
        total_ms: 7.45,
      },
      prompt_version: "v1.2.0",
    },
  },
  4: {
    responseText:
      "Access Denied: Pre-retrieval scope verification failed. Your technician token is only authorized for asset CP-204 at site SITE-A. Unauthorized asset query blocked.",
    attribution: {
      turn_id: 4,
      retrieval_id: "ret-denied-cp991",
      evidence_gate_decision: "FAIL_UNAUTHORIZED",
      grounding_status: "SKIPPED",
      retrieved_evidence: [],
      latencies: {
        normalization_ms: 0.14,
        authorization_ms: 0.09,
        retrieval_ms: 0.0,
        evidence_gate_ms: 0.23,
        total_ms: 0.46,
      },
      prompt_version: "v1.2.0",
    },
  },
};

export const LiveKitVoiceSession: React.FC<LiveKitVoiceSessionProps> = ({
  token,
  serverUrl,
  activeAsset,
  onAttributionUpdate,
  onDisconnect,
}) => {
  const [room, setRoom] = useState<Room | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isMicEnabled, setIsMicEnabled] = useState(false);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [statusMessage, setStatusMessage] = useState(
    serverUrl ? "Connecting to voice room..." : "Live voice service is not configured for this public demo."
  );

  useEffect(() => {
    let activeRoom: Room | null = null;

    async function connectRoom() {
      if (!serverUrl || !token) {
        setIsConnected(false);
        setStatusMessage("Live voice service is not configured for this public demo.");
        return;
      }

      try {
        activeRoom = new Room({
          adaptiveStream: true,
          dynacast: true,
        });

        activeRoom.on(RoomEvent.Connected, () => {
          setIsConnected(true);
          setIsMicEnabled(true);
          setStatusMessage("Voice pipeline connected. Speak hands-free.");
          setRoom(activeRoom);
        });

        activeRoom.on(RoomEvent.Disconnected, () => {
          setIsConnected(false);
          setStatusMessage("Voice session ended.");
          onDisconnect();
        });

        activeRoom.on(RoomEvent.TrackSubscribed, (track) => {
          if (track.kind === Track.Kind.Audio) {
            const el = track.attach();
            el.autoplay = true;
            document.body.appendChild(el);
            setAgentSpeaking(true);
          }
        });

        activeRoom.on(RoomEvent.TrackUnsubscribed, (track) => {
          track.detach().forEach((el) => el.remove());
          setAgentSpeaking(false);
        });

        activeRoom.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
          try {
            const str = new TextDecoder().decode(payload);
            const data = JSON.parse(str);
            if (data.type === "turn_attribution" && data.attribution) {
              onAttributionUpdate(data.attribution);

              if (data.response_text) {
                setMessages((prev) => [
                  ...prev,
                  {
                    id: `msg-${Date.now()}`,
                    role: "assistant",
                    text: data.response_text,
                    timestamp: new Date().toLocaleTimeString(),
                    attribution: data.attribution,
                  },
                ]);
              }
            }
          } catch (e) {
            // Non-JSON payload ignore
          }
        });

        await activeRoom.connect(serverUrl, token);
        await activeRoom.localParticipant.setMicrophoneEnabled(true);
      } catch (err: any) {
        console.warn("LiveKit connection note:", err);
        setIsConnected(false);
        setStatusMessage("Live voice service is not configured for this public demo.");
      }
    }

    connectRoom();

    return () => {
      if (activeRoom) {
        activeRoom.disconnect();
      }
    };
  }, [token, serverUrl]);

  const toggleMic = async () => {
    if (!room || !isConnected) {
      setStatusMessage("Live voice service is not configured for this public demo.");
      return;
    }
    const nextState = !isMicEnabled;
    await room.localParticipant.setMicrophoneEnabled(nextState);
    setIsMicEnabled(nextState);
  };

  const handleScenarioClick = (scenarioId: number, text: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `msg-${Date.now()}`,
        role: "user",
        text,
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);

    if (room && isConnected) {
      const payload = JSON.stringify({ type: "user_speech_text", text });
      room.localParticipant.publishData(new TextEncoder().encode(payload), { reliable: true });
      return;
    }

    // Demo mode: simulate assistant response with genuine evidence attribution
    const scenario = DEMO_SCENARIO_DATA[scenarioId];
    if (scenario) {
      setAgentSpeaking(true);
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          {
            id: `msg-${Date.now() + 1}`,
            role: "assistant",
            text: scenario.responseText,
            timestamp: new Date().toLocaleTimeString(),
            attribution: scenario.attribution,
          },
        ]);
        onAttributionUpdate(scenario.attribution);
        setAgentSpeaking(false);
      }, 350);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/90 rounded-xl border border-slate-800 p-4 space-y-4">
      {/* Session Top Bar */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              isConnected ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
            }`}
          />
          <span className="text-xs font-medium text-slate-300">{statusMessage}</span>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-xs px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-mono">
            Scope: {activeAsset}
          </span>
          <button
            onClick={onDisconnect}
            className="text-xs px-2.5 py-1 bg-rose-950/60 hover:bg-rose-900 border border-rose-800 text-rose-300 rounded-md transition-colors"
          >
            End Call
          </button>
        </div>
      </div>

      {/* Live Audio Visualizer / Status Orb */}
      <div className="flex items-center justify-center p-6 bg-slate-950/70 rounded-xl border border-slate-800/80 relative overflow-hidden">
        <div className="flex flex-col items-center space-y-3 z-10">
          <button
            onClick={toggleMic}
            className={`w-16 h-16 rounded-full flex items-center justify-center transition-all shadow-lg ${
              isMicEnabled && isConnected
                ? agentSpeaking
                  ? "bg-amber-500 text-slate-950 ring-4 ring-amber-400/30 scale-105"
                  : "bg-emerald-500 text-slate-950 ring-4 ring-emerald-400/30 hover:scale-105"
                : "bg-slate-700 text-slate-300 hover:bg-slate-600"
            }`}
          >
            {isMicEnabled && isConnected ? (
              agentSpeaking ? (
                <Volume2 className="w-8 h-8 animate-pulse" />
              ) : (
                <Mic className="w-8 h-8" />
              )
            ) : (
              <MicOff className="w-8 h-8" />
            )}
          </button>

          <span className="text-xs text-slate-400 font-medium flex items-center">
            {agentSpeaking ? (
              <span className="text-amber-400 flex items-center">
                <Activity className="w-3.5 h-3.5 mr-1 animate-spin" /> Copilot Responding
              </span>
            ) : isConnected && isMicEnabled ? (
              "Listening hands-free..."
            ) : (
              "Radio standby mode"
            )}
          </span>
        </div>
      </div>

      {/* Transcript Log */}
      <div className="flex-1 overflow-y-auto space-y-3 p-3 bg-slate-950/50 rounded-xl border border-slate-800 min-h-[160px]">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-slate-400">
            Click any Test Bench Scenario below to test deterministic Evidence Gating and Grounding.
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${
                m.role === "user" ? "items-end" : "items-start"
              }`}
            >
              <div
                className={`max-w-[85%] p-3 rounded-xl text-xs ${
                  m.role === "user"
                    ? "bg-blue-600 text-white rounded-br-none"
                    : "bg-slate-800 text-slate-100 rounded-bl-none border border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between text-[10px] opacity-75 mb-1 space-x-2">
                  <span className="font-semibold uppercase">{m.role}</span>
                  <span>{m.timestamp}</span>
                </div>
                <p className="leading-relaxed">{m.text}</p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Demo Scenario Shortcuts */}
      <div className="space-y-1.5 pt-1">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center">
          <Sparkles className="w-3 h-3 mr-1 text-amber-400" />
          Test Bench Scenarios (Evidence Gate Audit Prompts)
        </span>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() =>
              handleScenarioClick(
                1,
                "The compressor CP-204 is showing error E17. What should I check first?"
              )
            }
            className="p-2 text-left bg-slate-800/80 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors"
          >
            <span className="text-emerald-400 font-semibold block text-[10px]">SCENARIO 1: PASS</span>
            CP-204 showing error E17
          </button>
          <button
            onClick={() =>
              handleScenarioClick(
                2,
                "What is the high discharge procedure for model CP-300?"
              )
            }
            className="p-2 text-left bg-slate-800/80 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors"
          >
            <span className="text-amber-400 font-semibold block text-[10px]">SCENARIO 2: MODEL MISMATCH</span>
            Ask CP-300 on CP-204 unit
          </button>
          <button
            onClick={() =>
              handleScenarioClick(
                3,
                "What does error code E99 indicate on the compressor?"
              )
            }
            className="p-2 text-left bg-slate-800/80 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors"
          >
            <span className="text-rose-400 font-semibold block text-[10px]">SCENARIO 3: NO EVIDENCE</span>
            Unknown Error E99
          </button>
          <button
            onClick={() =>
              handleScenarioClick(
                4,
                "Query maintenance records for unauthorized asset CP-991."
              )
            }
            className="p-2 text-left bg-slate-800/80 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors"
          >
            <span className="text-rose-400 font-semibold block text-[10px]">SCENARIO 4: UNAUTHORIZED</span>
            Scope Escalation Block
          </button>
        </div>
      </div>
    </div>
  );
};
