import type { SeatPresentationMap } from './seatPresentation';

export type GameEvent = {
  seq: number;
  day: number;
  phase: string;
  type: string;
  actor: number | null;
  payload: Record<string, unknown>;
};

export type AgentSpec =
  | { kind: 'mock' }
  | {
      kind: 'llm';
      provider: 'mock' | 'litellm';
      model: string;
      base_url?: string;
      api_key?: string;
      api_key_env?: string;
      timeout_seconds?: number;
      thinking_enabled?: boolean;
    };

export type CreateGameResponse = {
  game_id: string;
};

export type GameListItem = {
  game_id: string;
  started_at: string | null;
  ended_at: string | null;
  winner: string | null;
  status: string;
  event_count: number;
};

export type GameTimings = Record<string, number>;

export type GameSummary = {
  game_id: string;
  status: string;
  winner: string | null;
  day: number;
  phase: string;
  event_count: number;
  timings: GameTimings;
  seat_presentation: SeatPresentationMap;
};

export type NarrativeRow = {
  seq: number;
  day: number;
  phase: string;
  kind: 'system' | 'speech' | 'action' | 'announce' | 'verdict';
  text: string;
  actor: number | null;
  icon: string | null;
};

export type SpectatorEffect = {
  seq: number;
  day: number;
  phase: string;
  kind:
    | 'guard_shield'
    | 'wolf_attack'
    | 'seer_vision'
    | 'witch_potion'
    | 'death_reveal';
  actor: number | null;
  source_seat: number | null;
  target_seat: number;
  asset_key: string;
  duration_ms: number;
  meta: Record<string, unknown>;
};

export type RoleReveal = {
  winner: string;
  seats: { seat: number; role: string; alive: boolean }[];
  highlights: { seq: number; summary: string }[];
};

export type ModelTestResponse = {
  ok: boolean;
  message: string | null;
};

const API_BASE =
  import.meta.env.VITE_WH_API_BASE?.replace(/\/+$/, '') ?? '';

export async function createGame(opts: {
  seed?: string;
  agents?: Record<number, AgentSpec>;
  pacing?: 'live' | 'fast' | 'off';
  seatPresentation?: SeatPresentationMap;
} = {}): Promise<CreateGameResponse> {
  const res = await fetch(`${API_BASE}/games`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      config_path: 'configs/games/classic_10.yaml',
      seed: opts.seed ?? `web-${Date.now()}`,
      agents: opts.agents ?? {},
      pacing: opts.pacing,
      seat_presentation: opts.seatPresentation ?? {},
    }),
  });
  return parseJsonResponse<CreateGameResponse>(res);
}

export async function getGame(gameId: string): Promise<GameSummary> {
  const res = await fetch(`${API_BASE}/games/${gameId}`);
  return parseJsonResponse<GameSummary>(res);
}

export async function listGames(): Promise<GameListItem[]> {
  const res = await fetch(`${API_BASE}/games`);
  return parseJsonResponse<GameListItem[]>(res);
}

export async function getEvents(gameId: string): Promise<GameEvent[]> {
  const res = await fetch(`${API_BASE}/games/${gameId}/events`);
  return parseJsonResponse<GameEvent[]>(res);
}

export async function getNarrative(
  gameId: string,
  after = 0,
): Promise<NarrativeRow[]> {
  const res = await fetch(`${API_BASE}/games/${gameId}/narrative?after=${after}`);
  return parseJsonResponse<NarrativeRow[]>(res);
}

export async function getEffects(
  gameId: string,
  after = 0,
): Promise<SpectatorEffect[]> {
  const res = await fetch(`${API_BASE}/games/${gameId}/effects?after=${after}`);
  return parseJsonResponse<SpectatorEffect[]>(res);
}

export async function getReveal(gameId: string): Promise<RoleReveal> {
  const res = await fetch(`${API_BASE}/games/${gameId}/reveal`);
  return parseJsonResponse<RoleReveal>(res);
}

export async function sendAck(
  gameId: string,
  phase: string,
  event: string,
  clientEventId = `${phase}:${event}:${Date.now()}`,
) {
  const res = await fetch(`${API_BASE}/games/${gameId}/ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phase, event, client_event_id: clientEventId }),
  });
  return parseJsonResponse<{ ok: boolean }>(res);
}

export async function submitSpeech(
  gameId: string,
  seat: number,
  text: string,
) {
  return postTextAction(gameId, 'speech', seat, text);
}

export async function submitWolfChat(
  gameId: string,
  seat: number,
  text: string,
) {
  return postTextAction(gameId, 'wolf_chat', seat, text);
}

export function subscribeGameEvents(
  gameId: string,
  onEvent: (event: GameEvent) => void,
  onError: () => void,
  onNarrative?: (row: NarrativeRow) => void,
  onEffect?: (effect: SpectatorEffect) => void,
  lastEventId?: number,
) {
  const params = lastEventId && lastEventId > 0
    ? `?last_event_id=${encodeURIComponent(String(lastEventId))}`
    : '';
  const source = new EventSource(`${API_BASE}/games/${gameId}/stream${params}`);
  source.addEventListener('game_event', (message) => {
    onEvent(JSON.parse((message as MessageEvent<string>).data) as GameEvent);
  });
  source.addEventListener('narrative_row', (message) => {
    onNarrative?.(JSON.parse((message as MessageEvent<string>).data) as NarrativeRow);
  });
  source.addEventListener('spectator_effect', (message) => {
    onEffect?.(JSON.parse((message as MessageEvent<string>).data) as SpectatorEffect);
  });
  source.onerror = onError;
  return source;
}

export async function testModelConnection(req: {
  provider?: 'mock' | 'litellm';
  model: string;
  base_url?: string;
  api_key?: string;
  timeout_seconds?: number;
  thinking_enabled?: boolean;
}, signal?: AbortSignal): Promise<ModelTestResponse> {
  const res = await fetch(`${API_BASE}/models/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });
  return parseJsonResponse<ModelTestResponse>(res);
}

async function postTextAction(
  gameId: string,
  kind: 'speech' | 'wolf_chat',
  seat: number,
  text: string,
) {
  const res = await fetch(`${API_BASE}/games/${gameId}/${kind}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seat, text }),
  });
  return parseJsonResponse<{ ok: boolean }>(res);
}

async function parseJsonResponse<T>(res: Response): Promise<T> {
  const data = (await res.json().catch(() => ({}))) as {
    code?: string;
    message?: string;
    details?: unknown;
  };
  if (!res.ok) {
    throw new Error(formatApiError(res.status, data));
  }
  return data as T;
}

function formatApiError(
  status: number,
  data: { code?: string; message?: string; details?: unknown },
) {
  const base = data.code
    ? `${data.code}: ${data.message ?? `HTTP ${status}`}`
    : data.message ?? `HTTP ${status}`;
  const details = summarizeDetails(data.details);
  return details ? `${base} (${details})` : base;
}

function summarizeDetails(details: unknown) {
  if (!details || typeof details !== 'object') {
    return '';
  }
  const errors = 'errors' in details ? details.errors : null;
  if (Array.isArray(errors)) {
    return errors
      .slice(0, 2)
      .map((error) => summarizeValidationError(error))
      .filter(Boolean)
      .join('; ');
  }
  try {
    return JSON.stringify(details).slice(0, 160);
  } catch {
    return '';
  }
}

function summarizeValidationError(error: unknown) {
  if (!error || typeof error !== 'object') {
    return '';
  }
  const loc = 'loc' in error && Array.isArray(error.loc)
    ? error.loc.join('.')
    : '';
  const msg = 'msg' in error && typeof error.msg === 'string'
    ? error.msg
    : '';
  return [loc, msg].filter(Boolean).join(': ');
}
