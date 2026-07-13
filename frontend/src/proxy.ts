import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next.js 16: Proxy (antes Middleware).
 * Check optimista de cookie/token en cliente; la autorización real está en el backend.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/dashboard")) {
    // El token vive en localStorage (SPA). No bloqueamos aquí para no romper SSR;
    // el layout cliente redirige a /login si falta sesión.
    return NextResponse.next();
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
