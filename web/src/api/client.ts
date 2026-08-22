/**
 * Talking to the Python server.
 *
 * Same-origin in both modes -- Vite proxies /api and /assets in development and
 * FastAPI serves the built page in production -- so there is no base URL to
 * configure and no CORS to grant.
 *
 * An error carries the server's own `detail` where there is one.  This project
 * spends a lot of effort on saying what happened rather than that something
 * did, and an interface that replaces "no replay with that id in the current
 * scan" with "Request failed" throws that away at the last step.
 */

import type { PositionsDoc } from "../model/replay";
import type {
  Config,
  Library,
  LibraryQuery,
  MapArt,
  MapSummary,
  Replay,
  SightMaskDoc,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response));
  }
  return (await response.json()) as T;
}

async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) {
      return body.detail;
    }
  } catch {
    // A non-JSON error body is not itself an error worth reporting; fall
    // through to the status line, which at least says what happened.
  }
  return `${response.status} ${response.statusText}`;
}

function queryString(query: LibraryQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const api = {
  config: () => get<Config>("/api/config"),
  library: (query: LibraryQuery = {}) => get<Library>(`/api/library${queryString(query)}`),
  replay: (id: string) => get<Replay>(`/api/replays/${encodeURIComponent(id)}`),
  // Separate from `replay` because the samples are three orders of magnitude
  // larger and because a replay is worth showing before they arrive.
  positions: (id: string) =>
    get<PositionsDoc>(`/api/replays/${encodeURIComponent(id)}/positions`),
  maps: () => get<MapSummary[]>("/api/maps"),
  map: (key: string) => get<MapArt>(`/api/maps/${encodeURIComponent(key)}`),
  // The playable silhouette a sight cone is raycast against, thresholded in
  // Python, with the sentence that says what it is travelling beside it. A map
  // with no radar image on disk 404s: the layer is unavailable, not empty.
  sight: (key: string) =>
    get<SightMaskDoc>(`/api/maps/${encodeURIComponent(key)}/sight`),
  closeReplay: (id: string) =>
    fetch(`/api/replays/${encodeURIComponent(id)}`, { method: "DELETE" }),
  decode: async (id: string): Promise<Replay> => {
    // Synchronous on purpose: the decode is about four seconds, which is
    // inside a request, so there is no job to poll and no stream to open.
    const response = await fetch(`/api/replays/${encodeURIComponent(id)}/decode`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new ApiError(response.status, await detailOf(response));
    }
    return (await response.json()) as Replay;
  },
};
