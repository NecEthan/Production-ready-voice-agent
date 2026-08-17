import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

export default function Signup({ onLogin }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const signupRes = await fetch("/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      if (!signupRes.ok) {
        const body = await signupRes.json().catch(() => ({}));
        const detail = body.detail;
        if (Array.isArray(detail)) {
          throw new Error(detail.map((d) => d.msg).join("; "));
        }
        throw new Error(detail || "Signup failed");
      }

      // Auto-login after signup
      const loginRes = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      const user = await loginRes.json();
      onLogin(user);
      navigate("/app");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>Peptide Voice Agent</h1>
      <form className="auth-form" onSubmit={handleSubmit}>
        <h2>Create account</h2>
        {error && <p className="auth-error">{error}</p>}
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            placeholder="Min 8 chars, uppercase, lowercase, digit"
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Creating account…" : "Sign up"}
        </button>
        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
