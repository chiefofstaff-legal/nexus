import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, getDemoPassword, validateCookie } from "@/lib/auth";

function isAuthenticated(request: NextRequest): boolean {
  if (!getDemoPassword()) return true;

  const cookie = request.cookies.get(COOKIE_NAME);
  if (!cookie) return false;

  return validateCookie(cookie.value);
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    pathname === "/login" ||
    pathname === "/api/auth/login" ||
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/favicon") ||
    pathname === "/health"
  ) {
    return NextResponse.next();
  }

  if (!isAuthenticated(request)) {
    // API calls get a JSON 401 so fetch() receives a parseable error,
    // not an HTML redirect that causes SyntaxError in the client.
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { detail: "Authentication required" },
        { status: 401 },
      );
    }
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
