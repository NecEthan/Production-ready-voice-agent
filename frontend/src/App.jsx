import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./Login";
import Signup from "./Signup";
import VoiceAgent from "./VoiceAgent";

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = loading, null = unauthed

  useEffect(() => {
    fetch("/auth/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => setUser(u))
      .catch(() => setUser(null));
  }, []);

  if (user === undefined) {
    return <div className="app-loading">Loading…</div>;
  }

  function handleLogout() {
    setUser(null);
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/app" replace /> : <Login onLogin={setUser} />} />
        <Route path="/signup" element={user ? <Navigate to="/app" replace /> : <Signup onLogin={setUser} />} />
        <Route
          path="/app"
          element={
            user
              ? <VoiceAgent user={user} onLogout={handleLogout} />
              : <Navigate to="/login" replace />
          }
        />
        <Route path="*" element={<Navigate to={user ? "/app" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
