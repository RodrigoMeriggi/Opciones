"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, ready, token } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin-change-me");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (ready && token) router.replace("/dashboard");
  }, [ready, token, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error de login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <div className="paper-banner mb-6 rounded-lg">MODO PAPER</div>
      <h1 className="font-[family-name:var(--font-display)] text-4xl text-[var(--ink)]">
        Opciones BYMA
      </h1>
      <p className="mt-2 text-[var(--muted)]">
        Acceso al panel de monitoreo. La validación de riesgo ocurre en el backend.
      </p>
      <form onSubmit={onSubmit} className="panel mt-8 space-y-4">
        <div>
          <label htmlFor="user">Usuario</label>
          <input id="user" value={username} onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div>
          <label htmlFor="pass">Contraseña</label>
          <input
            id="pass"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-[var(--danger)]">{error}</p> : null}
        <button className="btn w-full" disabled={loading} type="submit">
          {loading ? "Ingresando…" : "Ingresar"}
        </button>
        <p className="text-xs text-[var(--muted)]">
          Roles: admin / trader / viewer — cambiar credenciales en producción.
        </p>
      </form>
    </div>
  );
}
