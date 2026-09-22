// Pre-login screen. Isolated from app state on purpose: it only needs the
// auth form fields, health status and error display.
import { FormEvent } from "react";
import { HealthLine } from "../components/shared";
import type { HealthResponse } from "../types";

type AuthScreenProps = {
  health: HealthResponse | null;
  error: string;
  authMode: "login" | "register";
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
  setUsername: (value: string) => void;
  setEmail: (value: string) => void;
  setPassword: (value: string) => void;
  setConfirmPassword: (value: string) => void;
  setAuthMode: (mode: "login" | "register") => void;
  handleAuth: (event: FormEvent) => void;
};

export function AuthScreen({ health, error, authMode, username, email, password, confirmPassword, setUsername, setEmail, setPassword, setConfirmPassword, setAuthMode, handleAuth }: AuthScreenProps) {
  return (
    <main className="auth-screen">
      <section className="auth-card">
        <p className="eyebrow">Obsessive Solutions</p>
        <h1>Detalle obsesivo para agentes excepcionales.</h1>
        <p className="auth-copy">Entra a ObsyGPT para orquestar proveedores, agentes, skills, MCPs y trazas con precisión quirúrgica.</p>
        <HealthLine health={health} />
        <form onSubmit={handleAuth} className="auth-form">
          <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" aria-label="Usuario" required />
          {authMode === "register" && <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" required />}
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" aria-label="Contraseña" type="password" required />
          {authMode === "register" && <p className="muted">Password must be at least 8 characters and include letters and numbers.</p>}
          {authMode === "register" && <input value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Confirm password" type="password" required />}
          {error && <p className="error">{error}</p>}
          <button>{authMode === "login" ? "Entrar" : "Crear acceso"}</button>
        </form>
        <button className="text-button" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}>{authMode === "login" ? "¿Sin cuenta? Crear acceso" : "Ya tengo acceso"}</button>
      </section>
    </main>
  );
}
