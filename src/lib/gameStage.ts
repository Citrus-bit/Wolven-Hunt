export type DayPhase = 'day' | 'night';

export type GameStage = {
  dayNumber: number;
  phase: DayPhase;
};

export const INITIAL_STAGE: GameStage = {
  dayNumber: 1,
  phase: 'day',
};
