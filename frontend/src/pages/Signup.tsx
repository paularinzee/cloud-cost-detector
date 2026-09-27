import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, auth } from "../lib/api";

export default function Signup() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const { access_token } = await api.signup(email, password);
      auth.set(access_token);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-16">
      <div className="card">
        <h1 className="text-2xl font-semibold text-white mb-1">Create account</h1>
        <p className="text-sm text-slate-400 mb-6">
          Start detecting cloud cost waste in seconds.
        </p>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="label">Email</label>
            <input
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="label">Password</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              required
              minLength={8}
            />
          </div>
          <div>
            <label className="label">Confirm password</label>
            <input
              type="password"
              className="input"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat password"
              required
            />
          </div>

          {error && (
            <div className="text-sm text-sev-high bg-sev-high/10 border border-sev-high/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button className="btn-primary w-full" disabled={loading}>
            {loading ? "Creating…" : "Create account"}
          </button>
        </form>

        <p className="text-sm text-slate-400 mt-6 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
