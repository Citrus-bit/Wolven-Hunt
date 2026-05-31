import type { GameEvent } from './gameApi';

export type SeatRole = 'wolf' | 'villager' | 'seer' | 'witch' | 'guard';
export type IdentityCamp = 'wolf' | 'good';
export type HumanIdentityMarks = Partial<Record<number, SeatRole>>;

export type SeatIdentityBadge =
  | { kind: 'role'; role: SeatRole; source: 'true' | 'guess' }
  | { kind: 'camp'; camp: IdentityCamp; source: 'seer' };

export function normalizeHumanIdentityMarks(value: unknown): HumanIdentityMarks {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  const marks: HumanIdentityMarks = {};
  for (const [seat, role] of Object.entries(value)) {
    const seatNumber = Number(seat);
    if (Number.isInteger(seatNumber) && seatNumber >= 1 && seatNumber <= 10 && isSeatRole(role)) {
      marks[seatNumber] = role;
    }
  }
  return marks;
}

export function deriveSelfRoleInfo(events: GameEvent[]) {
  const start = events.find((event) => event.type === 'game_start');
  const role = typeof start?.payload.self_role === 'string'
    ? start.payload.self_role
    : null;
  const teammates = Array.isArray(start?.payload.teammates)
    ? start.payload.teammates
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0)
    : [];
  return {
    role: isSeatRole(role) ? role : null,
    teammates,
  };
}

export function deriveSeatIdentityBadges({
  events,
  humanSeat,
  humanIdentityMarks,
}: {
  events: GameEvent[];
  humanSeat: number | null;
  humanIdentityMarks: HumanIdentityMarks;
}): Partial<Record<number, SeatIdentityBadge>> {
  const badges: Partial<Record<number, SeatIdentityBadge>> = {};
  const revealedRoles = deriveRevealedSeatRoles(events);
  for (const [seat, role] of Object.entries(revealedRoles)) {
    if (role) {
      badges[Number(seat)] = { kind: 'role', role, source: 'true' };
    }
  }

  const selfRole = deriveSelfRoleInfo(events).role;
  if (humanSeat !== null && selfRole) {
    badges[humanSeat] = { kind: 'role', role: selfRole, source: 'true' };
  }

  const seerLocks = deriveSeerCampLocks(events);
  for (const [seat, camp] of Object.entries(seerLocks)) {
    const seatNumber = Number(seat);
    if (camp && !badges[seatNumber]) {
      badges[seatNumber] = { kind: 'camp', camp, source: 'seer' };
    }
  }

  for (const [seat, role] of Object.entries(humanIdentityMarks)) {
    const seatNumber = Number(seat);
    if (role && !badges[seatNumber]) {
      badges[seatNumber] = { kind: 'role', role, source: 'guess' };
    }
  }

  return badges;
}

export function deriveRevealedSeatRoles(events: GameEvent[]): Partial<Record<number, SeatRole>> {
  const roles: Partial<Record<number, SeatRole>> = {};
  for (const event of events) {
    if (event.type === 'game_start') {
      const assignment = event.payload.role_assignment;
      if (assignment && typeof assignment === 'object' && !Array.isArray(assignment)) {
        for (const [seat, role] of Object.entries(assignment as Record<string, unknown>)) {
          if (isSeatRole(role)) {
            roles[Number(seat)] = role;
          }
        }
      }
    }
    if (event.type === 'role_reveal' && Array.isArray(event.payload.seats)) {
      for (const seatInfo of event.payload.seats) {
        if (!seatInfo || typeof seatInfo !== 'object') {
          continue;
        }
        const seat = 'seat' in seatInfo ? Number(seatInfo.seat) : NaN;
        const role = 'role' in seatInfo ? seatInfo.role : null;
        if (Number.isFinite(seat) && isSeatRole(role)) {
          roles[seat] = role;
        }
      }
    }
  }
  return roles;
}

export function deriveSeerCampLocks(events: GameEvent[]): Partial<Record<number, IdentityCamp>> {
  const locks: Partial<Record<number, IdentityCamp>> = {};
  for (const event of events) {
    if (event.type !== 'seer_check_result') {
      continue;
    }
    const target = Number(event.payload.target);
    const rawCamp = event.payload.camp ?? event.payload.result;
    if (Number.isInteger(target) && target > 0 && isIdentityCamp(rawCamp)) {
      locks[target] = rawCamp;
    }
  }
  return locks;
}

export function isSeatRole(value: unknown): value is SeatRole {
  return (
    value === 'wolf' ||
    value === 'villager' ||
    value === 'seer' ||
    value === 'witch' ||
    value === 'guard'
  );
}

function isIdentityCamp(value: unknown): value is IdentityCamp {
  return value === 'wolf' || value === 'good';
}
