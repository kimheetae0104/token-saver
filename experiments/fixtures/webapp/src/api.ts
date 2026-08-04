// HTTP 래퍼 — 픽스처
const BASE = "https://example.test";

export function httpGet(path: string): Promise<any> {
  return fetch(BASE + path).then((r) => r.json());
}

export function httpPost(path: string, body: unknown): Promise<any> {
  return fetch(BASE + path, {
    method: "POST",
    body: JSON.stringify(body),
  }).then((r) => r.json());
}

export const buildUrl = (path: string): string => BASE + path; // arrow export (함정: const arrow)

function normalizeError(e: unknown): string {
  return String(e); // 비-export
}

export function httpDelete(path: string): Promise<any> {
  return fetch(BASE + path, { method: "DELETE" })
    .then((r) => r.json())
    .catch((e) => ({ error: normalizeError(e) }));
}
