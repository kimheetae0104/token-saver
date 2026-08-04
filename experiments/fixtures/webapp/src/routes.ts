// 라우트 정의 — 픽스처
import { currentToken } from "./auth";

export function registerRoutes(app: { get: Function; post: Function }): void {
  app.get("/health", () => ({ ok: true }));
  app.post("/echo", (b: unknown) => b);
}

export function requireAuth(next: Function): Function {
  return (...args: unknown[]) => {
    if (!currentToken()) throw new Error("unauthorized");
    return next(...args);
  };
}

export default function bootstrap(): string {
  return "booted"; // default export 함수 (함정)
}
