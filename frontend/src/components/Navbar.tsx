import { Link, useLocation, useNavigate } from "react-router-dom";
import { auth } from "../lib/api";

export default function Navbar() {
  const nav = useNavigate();
  const loc = useLocation();
  const authed = auth.isAuthed();

  const logout = () => {
    auth.clear();
    nav("/login");
  };

  const linkCls = (path: string) =>
    `px-3 py-1.5 rounded-md text-sm transition-colors ${
      loc.pathname === path
        ? "bg-bg-soft text-white"
        : "text-slate-400 hover:text-slate-100"
    }`;

  return (
    <header className="border-b border-bg-border bg-bg-soft/60 backdrop-blur sticky top-0 z-20">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 font-semibold text-white">
          <span className="w-2 h-2 rounded-full bg-accent shadow-[0_0_12px_rgba(124,92,255,0.8)]" />
          AI Cloud Cost Detective
        </Link>

        <nav className="flex items-center gap-1">
          {authed ? (
            <>
              <Link to="/" className={linkCls("/")}>Dashboard</Link>
              <Link to="/history" className={linkCls("/history")}>History</Link>
              <button onClick={logout} className="ml-2 btn-ghost text-sm">
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className={linkCls("/login")}>Log in</Link>
              <Link to="/signup" className={linkCls("/signup")}>Sign up</Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}