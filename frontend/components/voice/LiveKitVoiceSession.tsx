"use client";

import React, { useState, useEffect, useRef } from "react";
import { Room, RoomEvent, Track, RemoteParticipant } from "livekit-client";
import { Mic, MicOff, Volume2, Radio, Activity, AlertCircle, Sparkles } from "lucide-react";
import { VoiceMessage, TurnAttribution } from "@/types";

interface LiveKitVoiceSessionProps {
  token: string;
  serverUrl: string;
  activeAsset: string;
  onAttributionUpdate: (attr: TurnAttribution) => void;
  onDisconnect: () => void;
}

export const LiveKitVoiceSession: React.FC<LiveKitVoiceSessionProps> = ({
  token,
  serverUrl,
  activeAsset,
  onAttributionUpdate,
  onDisconnect,
}) => {
  const [room, setRoom] = useState<Room | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isMicEnabled, setIsMicEnabled] = useState(true);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [statusMessage, setStatusMessage] = useState("Connecting to voice room...");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let activeRoom: Room | null = null;

    async function connectRoom() {
      try {
        activeRoom = new Room({
          adaptiveStream: true,
          dynacast: true,
        });

        activeRoom.on(RoomEvent.Connected, () => {
          setIsConnected(true);
          setStatusMessage("Voice pipeline connected. Speak hands-free.");
          setRoom(activeRoom);
        });

        activeRoom.on(RoomEvent.Disconnected, () => {
          setIsConnected(false);
          setStatusMessage("Voice session ended.");
          onDisconnect();
        });

        activeRoom.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
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

        // Listen for Realtime Turn Attribution Metadata from Agent
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
            // Ignore non-json data
          }
        });

        await activeRoom.connect(serverUrl, token);
        await activeRoom.localParticipant.setMicrophoneEnabled(true);
      } catch (err: any) {
        console.error("LiveKit connection error:", err);
        setStatusMessage(`Connection failed: ${err.message || "Could not reach LiveKit server"}`);
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
    if (!room) return;
    const nextState = !isMicEnabled;
    await room.localParticipant.setMicrophoneEnabled(nextState);
    setIsMicEnabled(nextState);
  };

  const sendSimulatedUtterance = (text: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `msg-${Date.now()}`,
        role: "user",
        text,
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);

    // Send text query via LiveKit data channel if active
    if (room && isConnected) {
      const payload = JSON.stringify({ type: "user_speech_text", text });
      room.localParticipant.publishData(new TextEncoder().encode(payload), { reliable: true });
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/90 rounded-xl border border-slate-800 p-4 space-y-4">
      {/* Session Top Bar */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <div className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
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
              isMicEnabled
                ? agentSpeaking
                  ? "bg-amber-500 text-slate-950 ring-4 ring-amber-400/30 scale-105"
                  : "bg-emerald-500 text-slate-950 ring-4 ring-emerald-400/30 hover:scale-105"
                : "bg-slate-700 text-slate-300 hover:bg-slate-600"
            }`}
          >
            {isMicEnabled ? (
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
                <Activity className="w-3.5 h-3.5 mr-1 animate-spin" /> Copilot Speaking (Barge-in enabled)
              </span>
            ) : isMicEnabled ? (
              "Listening hands-free..."
            ) : (
              "Microphone muted"
            )}
          </span>
        </div>
      </div>

      {/* Transcript Log */}
      <div className="flex-1 overflow-y-auto space-y-3 p-3 bg-slate-950/50 rounded-xl border border-slate-800 min-h-[160px]">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-slate-400">
            Microphone active. Say: "The compressor CP-204 is showing error E17. What should I check first?"
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
          Test Bench Scenarios (Quick Audio Prompts)
        </span>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() =>
              sendSimulatedUtterance("The compressor CP-204 is showing error E17. What should I check first?")
            }
            className="p-2 text-left bg-slate-800/80 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors"
          >
            <span className="text-emerald-400 font-semibold block text-[10px]">SCENARIO 1: PASS</span>
            CP-204 showing error E17
          </button>
          <button
            onClick={() =>
              sendSimulatedUtterance("What is the high discharge procedure for model CP-300?")
            }
            className="p-2 text-left bg-slate-800/80 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors"
          >
            <span className="text-amber-400 font-semibold block text-[10px]">SCENARIO 2: MODEL MISMATCH</span>
            Ask CP-300 on CP-204 unit
          </button>
          <button
            onClick={() =>
              sendSimulatedUtterance("What does error code E99 indicate on the compressor?")
            }
            className="p-2 text-left bg-slate-800/80 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors"
          >
            <span className="text-rose-400 font-semibold block text-[10px]">SCENARIO 3: NO EVIDENCE</span>
            Unknown Error E99
          </button>
          <button
            onClick={() =>
              sendSimulatedUtterance("Query maintenance records for unauthorized asset CP-991.")
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
