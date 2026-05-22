export type GameEvent = {
  seq: number;
  day: number;
  phase: string;
  type: string;
  actor: number | null;
  payload: Record<string, unknown>;
};

export type CreateGameResponse = {
  game_id: string;
};

export type GameSummary = {
  game_id: string;
  status: string;
  winner: string | null;
  day: number;
  phase: string;
  event_count: number;
};

const API_BASE =
  import.meta.env.VITE_WH_API_BASE?.replace(/\/+$/, '') ??
  'http://localhost:8000';

export async function createGame(seed?: string): Promise<CreateGameResponse> {
  const res = await fetch(`${API_BASE}/games`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      config_path: 'configs/games/classic_8.yaml',
      seed: seed ?? `web-${Date.now()}`,
      agents: {},
    }),
  });
  return parseJsonResponse<CreateGameResponse>(res);
}

export async function getGame(gameId: string): Promise<GameSummary> {
  const res = await fetch(`${API_BASE}/games/${gameId}`);
  return parseJsonResponse<GameSummary>(res);
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
) {
  const source = new EventSource(`${API_BASE}/games/${gameId}/stream`);
  source.addEventListener('game_event', (message) => {
    onEvent(JSON.parse((message as MessageEvent<string>).data) as GameEvent);
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
