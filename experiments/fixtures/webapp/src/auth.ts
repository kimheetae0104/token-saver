// 인증 모듈 — 픽스처 (TS 프로젝트 유형)
import { httpGet, httpPost } from "./api";

const TOKEN_KEY = "auth_token";

export function login(user: string, pass: string): Promise<string> {
  return httpPost("/login", { user, pass }).then((r) => r.token);
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function currentToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function refreshInternal(t: string): string {
  return t + ".refreshed"; // 비-export 헬퍼 (정답에서 제외돼야 함)
}

export async function refreshToken(): Promise<string | null> {
  const t = currentToken();
  if (!t) return null;
  const next = refreshInternal(t);
  await httpGet("/ping");
  return next;
}
