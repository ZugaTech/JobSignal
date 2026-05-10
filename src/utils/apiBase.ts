/**
 * API origin for /v1/verify. Prefer Vite env, then window.JOBSIGNAL_API_BASE, then same-host heuristics.
 */
export function resolveApiBase(): string {
  const fromEnv = (import.meta.env.VITE_API_BASE ?? "").trim();
  if (fromEnv) {
    return fromEnv.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    const w = (window as unknown as { JOBSIGNAL_API_BASE?: string }).JOBSIGNAL_API_BASE;
    if (typeof w === "string" && w.trim()) {
      return w.replace(/\/$/, "");
    }
  }
  if (typeof window === "undefined") {
    return "";
  }
  const h = window.location.hostname;
  const protocol = window.location.protocol;
  const port = window.location.port;

  if (protocol === "file:" || h === "") {
    return "http://127.0.0.1:8080";
  }
  if ((h === "localhost" || h === "127.0.0.1") && port === "8080") {
    return "";
  }
  if (h === "localhost" || h === "127.0.0.1") {
    return "http://127.0.0.1:8080";
  }
  return "";
}
