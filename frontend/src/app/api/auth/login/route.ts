import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, hashPassword, getDemoPassword } from "@/lib/auth";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { password } = body;

  const expected = getDemoPassword();
  if (!expected) {
    return NextResponse.json({ error: "No demo password configured" }, { status: 500 });
  }

  if (password !== expected) {
    return NextResponse.json({ error: "Incorrect password" }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(COOKIE_NAME, hashPassword(expected), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });

  return response;
}
