import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const PASSCODE = process.env.DEMO_PASSCODE ?? "";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const { passcode } = body as { passcode?: string };

  if (!PASSCODE || passcode === PASSCODE) {
    const jar = await cookies();
    jar.set("demo_auth", PASSCODE || "open", {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24, // 24 hours
    });
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ ok: false, error: "Неверный пароль" }, { status: 401 });
}
