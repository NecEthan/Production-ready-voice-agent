import { useState, useCallback, useEffect, useRef } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  useLocalParticipant,
  useRoomContext,
} from "@livekit/components-react";
import { RoomEvent } from "livekit-client";

const ROOM_NAME = "demo";

function VoiceUI({ onDisconnect }) {
  const { state: agentState } = useVoiceAssistant();
  const { localParticipant } = useLocalParticipant();
  const room = useRoomContext();
  const [muted, setMuted] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    const handler = (segments, participant) => {
      const role = participant.identity === localParticipant.identity ? "user" : "agent";
      setTranscript((prev) => {
        const next = [...prev];
        for (const seg of segments) {
          const idx = next.findIndex((m) => m.id === seg.id);
          if (idx >= 0) {
            next[idx] = { ...next[idx], text: seg.text, final: seg.final };
          } else {
            next.push({ id: seg.id, role, text: seg.text, final: seg.final });
          }
        }
        return next;
      });
    };
    room.on(RoomEvent.TranscriptionReceived, handler);
    return () => room.off(RoomEvent.TranscriptionReceived, handler);
  }, [room, localParticipant.identity]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  const toggleMic = useCallback(async () => {
    await localParticipant.setMicrophoneEnabled(muted);
    setMuted((m) => !m);
  }, [localParticipant, muted]);

  const stateLabel = {
    disconnected: "idle",
    connecting: "connecting…",
    initializing: "initializing…",
    listening: "listening",
    thinking: "thinking",
    speaking: "speaking",
  }[agentState] ?? agentState;

  const isActive = agentState === "speaking" || agentState === "thinking";

  return (
    <div className="voice-ui">
      <RoomAudioRenderer />

      <div className={`agent-state ${agentState}`}>
        <div className="state-dot" />
        <span>{stateLabel}</span>
        {isActive && (
          <div className="bars">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="bar" style={{ animationDelay: `${i * 0.1}s` }} />
            ))}
          </div>
        )}
      </div>

      <div className="transcript">
        {transcript.length === 0 && (
          <p className="transcript-empty">Conversation will appear here…</p>
        )}
        {transcript.map((msg) => (
          <div key={msg.id} className={`bubble ${msg.role} ${msg.final ? "final" : "interim"}`}>
            <span className="bubble-label">{msg.role === "user" ? "You" : "Agent"}</span>
            <span className="bubble-text">{msg.text}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <button className="mic-btn" onClick={toggleMic}>
        {muted ? "Unmute mic" : "Mute mic"}
      </button>
    </div>
  );
}

export default function VoiceAgent({ user, onLogout }) {
  const [token, setToken] = useState(null);
  const [url, setUrl] = useState(null);
  const [connecting, setConnecting] = useState(false);

  const connect = useCallback(async () => {
    setConnecting(true);
    try {
      const res = await fetch(`/token?room=${ROOM_NAME}`, { credentials: "include" });
      if (!res.ok) throw new Error("Token request failed");
      const data = await res.json();
      setUrl(data.url);
      setToken(data.token);
    } catch (err) {
      console.error("Token fetch failed:", err);
    } finally {
      setConnecting(false);
    }
  }, []);

  const disconnect = useCallback(() => {
    setToken(null);
    setUrl(null);
  }, []);

  async function handleLogout() {
    await fetch("/auth/logout", { method: "POST", credentials: "include" });
    onLogout();
  }

  return (
    <div className="app">
      <div className="app-header">
        <h1>Peptide Voice Agent</h1>
        <div className="app-header-right">
          <span className="app-user">{user.email}</span>
          <button className="logout-btn" onClick={handleLogout}>Sign out</button>
        </div>
      </div>

      {!token ? (
        <button className="connect-btn" onClick={connect} disabled={connecting}>
          {connecting ? "Connecting…" : "Connect"}
        </button>
      ) : (
        <>
          <LiveKitRoom
            token={token}
            serverUrl={url}
            connect={true}
            audio={true}
            video={false}
          >
            <VoiceUI onDisconnect={disconnect} />
          </LiveKitRoom>
          <button className="disconnect-btn" onClick={disconnect}>
            Disconnect
          </button>
        </>
      )}
    </div>
  );
}
