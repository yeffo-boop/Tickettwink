import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";

export default function Login() {
  const { loginSandbox } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSandboxLogin() {
    setBusy(true);
    setError(null);
    try {
      await loginSandbox();
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="logo">🎟️💅</div>
        <h1>Ticket Twink</h1>
        <p className="tagline">Movie nights, minus the spreadsheet.</p>

        <button className="btn btn-primary" onClick={handleSandboxLogin} disabled={busy}>
          {busy ? "Signing in…" : "Sandbox Sign-In (dev)"}
        </button>
        <p className="hint">
          Real accounts sign in with Telegram. Sandbox mode is enabled because this deployment has no
          TELEGRAM_BOT_TOKEN configured yet — see docs/SETUP.md.
        </p>
        {error && <p className="error-text">{error}</p>}
      </div>
    </div>
  );
}
