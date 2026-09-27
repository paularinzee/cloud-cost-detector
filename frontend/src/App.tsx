import { Navigate, Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import Login from "./pages/Login";
import Report from "./pages/Report";
import Signup from "./pages/Signup";
import { auth } from "./lib/api";

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!auth.isAuthed()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/report/:id" element={<RequireAuth><Report /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><History /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}