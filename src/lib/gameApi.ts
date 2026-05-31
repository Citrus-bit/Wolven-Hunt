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
  player_token: string | null;
  human_seat: number | null;
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

export type HumanRole = 'villager' | 'witch' | 'seer' | 'guard' | 'wolf' | 'random';

export type TurnRequest = {
  seat: number;
  kind:
    | 'guard'
    | 'wolf_chat'
    | 'wolf_vote'
    | 'seer'
    | 'witch'
    | 'speech'
    | 'vote'
    | 'pk_vote'
    | 'last_words';
  deadline_ts: number;
  timeout_seconds: number;
  valid_targets: number[] | null;
  constraints: Record<string, unknown>;
  phase: string;
  day: number;
};

export type SeatActionRequest =
  | { kind: 'speech' | 'wolf_chat' | 'last_words'; text: string }
  | { kind: 'guard' | 'seer' | 'wolf_vote'; target: number }
  | { kind: 'vote' | 'pk_vote'; target: number | null }
  | { kind: 'witch'; action: 'save' | 'poison' | 'skip'; target: number | null };

export type RoleReveal = {
  winner: string;
  seats: { seat: number; role: string; alive: boolean }[];
  highlights: { seq: number; summary: string }[];
};

export type ReviewReport = {
  schema_version: string;
  game_id: string;
  generated_at: string;
  generation_mode: 'real_ai' | 'offline_mock';
  summary: {
    winner: string;
    verdict: string;
    turning_points: string[];
    overall_assessment: string;
  };
  leaderboard: {
    rank: number;
    seat: number;
    nickname: string;
    role: string;
    camp: string;
    overall_score: number;
    reason: string;
  }[];
  players: {
    seat: number;
    nickname: string;
    role: string;
    camp: string;
    alive: boolean;
    scores: {
      key:
        | 'speech'
        | 'reasoning'
        | 'voting'
        | 'camp_contribution'
        | 'information_control'
        | 'role_duty';
      label: string;
      value: number;
    }[];
    overall_score: number;
    evaluation: string;
    evidence: string[];
    strengths: string[];
    mistakes: string[];
    suggestions: string[];
  }[];
  key_decisions: {
    day: number;
    phase: string;
    seq: number | null;
    title: string;
    analysis: string;
    impact: string;
  }[];
  counterfactuals: {
    premise: string;
    likely_outcome: string;
    lesson: string;
  }[];
};

export type ModelTestResponse = {
  ok: boolean;
  message: string | null;
};

const API_BASE =
  import.meta.env.VITE_WH_API_BASE?.replace(/\/+$/, '') ?? '';

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/healthz`, {
      method: 'GET',
      cache: 'no-store',
    });
    if (!res.ok) {
      return false;
    }
    const data = (await res.json().catch(() => null)) as { ok?: unknown } | null;
    return data?.ok === true;
  } catch {
    return false;
  }
}

export async function createGame(opts: {
  seed?: string;
  agents?: Record<number, AgentSpec>;
  pacing?: 'live' | 'fast' | 'off';
  startPaused?: boolean;
  seatPresentation?: SeatPresentationMap;
  evolutionEnabled?: boolean;
  humanSeat?: number;
  humanSeatRandom?: boolean;
  humanRole?: HumanRole;
} = {}): Promise<CreateGameResponse> {
  const res = await fetch(`${API_BASE}/games`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      config_path: 'configs/games/classic_10.yaml',
      seed: opts.seed ?? `web-${Date.now()}`,
      agents: opts.agents ?? {},
      pacing: opts.pacing,
      start_paused: opts.startPaused ?? false,
      seat_presentation: opts.seatPresentation ?? {},
      evolution_enabled: opts.evolutionEnabled ?? false,
      human_seat: opts.humanSeat,
      human_seat_random: opts.humanSeatRandom ?? false,
      human_role: opts.humanRole ?? 'random',
    }),
  });
  return parseJsonResponse<CreateGameResponse>(res);
}

export async function runGame(gameId: string): Promise<GameSummary> {
  const res = await fetch(`${API_BASE}/games/${gameId}/run`, {
    method: 'POST',
  });
  return parseJsonResponse<GameSummary>(res);
}

export async function pauseGame(gameId: string): Promise<GameSummary> {
  const res = await fetch(`${API_BASE}/games/${gameId}/pause`, {
    method: 'POST',
  });
  return parseJsonResponse<GameSummary>(res);
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

export async function getReviewReport(gameId: string): Promise<ReviewReport> {
  const res = await fetch(`${API_BASE}/games/${gameId}/review-report`);
  return parseJsonResponse<ReviewReport>(res);
}

export async function generateReviewReport(gameId: string): Promise<ReviewReport> {
  const res = await fetch(`${API_BASE}/games/${gameId}/review-report`, {
    method: 'POST',
  });
  return parseJsonResponse<ReviewReport>(res);
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

export function spectatorEffectAckEvent(seq: number) {
  return `spectator_effect_rendered:${seq}`;
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

export async function submitSeatAction(
  gameId: string,
  seat: number,
  playerToken: string,
  action: SeatActionRequest,
) {
  const res = await fetch(
    `${API_BASE}/games/${gameId}/seat/${seat}/action?player_token=${encodeURIComponent(playerToken)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(action),
    },
  );
  return parseJsonResponse<{ ok: boolean }>(res);
}

export function subscribeGameEvents(
  gameId: string,
  onOpen: () => void,
  onReady: () => void,
  onEvent: (event: GameEvent, streamCursor: number | null) => void,
  onError: () => void,
  onNarrative?: (row: NarrativeRow, streamCursor: number | null) => void,
  onEffect?: (effect: SpectatorEffect, streamCursor: number | null) => void,
  lastEventId?: number,
) {
  const params = lastEventId && lastEventId > 0
    ? `?last_event_id=${encodeURIComponent(String(lastEventId))}`
    : '';
  const source = new EventSource(`${API_BASE}/games/${gameId}/stream${params}`);
  source.onopen = () => {
    onOpen();
    onReady();
  };
  source.addEventListener('stream_ready', () => {
    onReady();
  });
  source.addEventListener('game_event', (message) => {
    const eventMessage = message as MessageEvent<string>;
    onEvent(
      JSON.parse(eventMessage.data) as GameEvent,
      parseEventSourceCursor(eventMessage.lastEventId),
    );
  });
  source.addEventListener('narrative_row', (message) => {
    const eventMessage = message as MessageEvent<string>;
    onNarrative?.(
      JSON.parse(eventMessage.data) as NarrativeRow,
      parseEventSourceCursor(eventMessage.lastEventId),
    );
  });
  source.addEventListener('spectator_effect', (message) => {
    const eventMessage = message as MessageEvent<string>;
    onEffect?.(
      JSON.parse(eventMessage.data) as SpectatorEffect,
      parseEventSourceCursor(eventMessage.lastEventId),
    );
  });
  source.onerror = onError;
  return source;
}

export function subscribeSeatEvents(
  gameId: string,
  seat: number,
  playerToken: string,
  onOpen: () => void,
  onReady: () => void,
  onEvent: (event: GameEvent, streamCursor: number | null) => void,
  onError: () => void,
  onTurnRequest: (turn: TurnRequest) => void,
  onTurnCleared: () => void,
  onNarrative?: (row: NarrativeRow, streamCursor: number | null) => void,
  onEffect?: (effect: SpectatorEffect, streamCursor: number | null) => void,
  lastEventId?: number,
) {
  const params = new URLSearchParams({ player_token: playerToken });
  if (lastEventId && lastEventId > 0) {
    params.set('last_event_id', String(lastEventId));
  }
  const source = new EventSource(
    `${API_BASE}/games/${gameId}/seat/${seat}/stream?${params.toString()}`,
  );
  source.onopen = () => {
    onOpen();
    onReady();
  };
  source.addEventListener('stream_ready', () => {
    onReady();
  });
  source.addEventListener('game_event', (message) => {
    const eventMessage = message as MessageEvent<string>;
    onEvent(
      JSON.parse(eventMessage.data) as GameEvent,
      parseEventSourceCursor(eventMessage.lastEventId),
    );
  });
  source.addEventListener('narrative_row', (message) => {
    const eventMessage = message as MessageEvent<string>;
    onNarrative?.(
      JSON.parse(eventMessage.data) as NarrativeRow,
      parseEventSourceCursor(eventMessage.lastEventId),
    );
  });
  source.addEventListener('spectator_effect', (message) => {
    const eventMessage = message as MessageEvent<string>;
    onEffect?.(
      JSON.parse(eventMessage.data) as SpectatorEffect,
      parseEventSourceCursor(eventMessage.lastEventId),
    );
  });
  source.addEventListener('turn_request', (message) => {
    const eventMessage = message as MessageEvent<string>;
    onTurnRequest(JSON.parse(eventMessage.data) as TurnRequest);
  });
  source.addEventListener('turn_cleared', () => {
    onTurnCleared();
  });
  source.onerror = onError;
  return source;
}

export function parseEventSourceCursor(lastEventId: string) {
  if (!lastEventId) {
    return null;
  }
  const cursor = Number(lastEventId);
  return Number.isInteger(cursor) && cursor > 0 ? cursor : null;
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
