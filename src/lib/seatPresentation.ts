import { MODEL_SLOTS } from './modelConfigs';

export type SeatPresentation = {
  nickname: string;
  icon_path: string;
};

export type SeatPresentationMap = Record<number, SeatPresentation>;

export type SeatDisplay = {
  nickname: string;
  iconPath: string;
};

export const HUMAN_SEAT_PRESENTATION: SeatPresentation = {
  nickname: '你自己',
  icon_path: '/assets/lobby/human_player.png',
};

export function buildSeatPresentation(
  assignments: (number | null)[],
  opts: { humanSeatIndex?: number | null } = {},
): SeatPresentationMap {
  const presentation: SeatPresentationMap = {};
  assignments.forEach((slotIndex, seatIndex) => {
    if (opts.humanSeatIndex === seatIndex) {
      presentation[seatIndex + 1] = HUMAN_SEAT_PRESENTATION;
      return;
    }
    if (slotIndex === null) {
      return;
    }
    const slot = MODEL_SLOTS[slotIndex];
    if (!slot) {
      return;
    }
    presentation[seatIndex + 1] = {
      nickname: slot.nickname,
      icon_path: slot.iconPath,
    };
  });
  return presentation;
}

export function resolveSeatDisplay(
  seatNumber: number,
  assignments: (number | null)[],
  seatPresentation: SeatPresentationMap,
): SeatDisplay | null {
  const slotIndex = assignments[seatNumber - 1];
  if (slotIndex !== null && slotIndex !== undefined) {
    const slot = MODEL_SLOTS[slotIndex];
    if (slot) {
      return {
        nickname: slot.nickname,
        iconPath: slot.iconPath,
      };
    }
  }
  const presentation = seatPresentation[seatNumber];
  if (presentation) {
    return {
      nickname: presentation.nickname,
      iconPath: presentation.icon_path,
    };
  }
  return null;
}
