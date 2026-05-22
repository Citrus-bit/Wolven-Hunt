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
    };

export type CreateGameResponse = {
  game_id: string;
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

export type RoleReveal = {
  winner: string;
  seats: { seat: number; role: string; alive: boolean }[];
  highlights: { seq: number; summary: string }[];
};

const API_BASE =
  import.meta.env.VITE_WH_API_BASE?.replace(/\/+$/, '') ??
  'http://localhost:8000';

export async function createGame(opts: {
  seed?: string;
  agents?: Record<number, AgentSpec>;
  pacing?: 'live' | 'fast' | 'off';
} = {}): Promise<CreateGameResponse> {
  const res = await fetch(`${API_BASE}/games`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      config_path: 'configs/games/classic_8.yaml',
      seed: opts.seed ?? `web-${Date.now()}`,
      agents: opts.agents ?? {},
      pacing: opts.pacing,
    }),
  });
  return parseJsonResponse<CreateGameResponse>(res);
}

export async function getGame(gameId: string): Promise<GameSummary> {
  const res = await fetch(`${API_BASE}/games/${gameId}`);
  return parseJsonResponse<GameSummary>(res);
}

export async function getNarrative(
  gameId: string,
  after = 0,
): Promise<NarrativeRow[]> {
  const res = await fetch(`${API_BASE}/games/${gameId}/narrative?after=${after}`);
  return parseJsonResponse<NarrativeRow[]>(res);
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
) {
  const source = new EventSource(`${API_BASE}/games/${gameId}/stream`);
  source.addEventListener('game_event', (message) => {
    onEvent(JSON.parse((message as MessageEvent<string>).data) as GameEvent);
  });
  source.addEventListener('narrative_row', (message) => {
    onNarrative?.(JSON.parse((message as MessageEvent<string>).data) as NarrativeRow);
  });
  source.onerror = onError;
  return source;
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
  };
  if (!res.ok) {
    throw new Error(data.message || data.code || `HTTP ${res.status}`);
  }
  return data as T;
}
