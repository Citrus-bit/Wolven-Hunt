export type GameAudioKey =
  | 'wolf_howl'
  | 'night_guard'
  | 'night_wolves'
  | 'night_seer'
  | 'day_rooster'
  | 'day_dawn'
  | 'day_death'
  | 'day_peaceful';

export type GameVideoKey = 'knight_duel';

const AUDIO_PATHS: Record<GameAudioKey, string> = {
  wolf_howl: '/assets/game/audio/wolf_howl.mp3',
  night_guard: '/assets/game/audio/night_guard.mp3',
  night_wolves: '/assets/game/audio/night_wolves.mp3',
  night_seer: '/assets/game/audio/night_seer.mp3',
  day_rooster: '/assets/game/audio/day_rooster.mp3',
  day_dawn: '/assets/game/audio/day_dawn.mp3',
  day_death: '/assets/game/audio/day_death.mp3',
  day_peaceful: '/assets/game/audio/day_peaceful.mp3',
};

const VIDEO_PATHS: Record<GameVideoKey, string> = {
  knight_duel: '/assets/game/video/knight_duel.mp4',
};

export function gameAudioPath(key: GameAudioKey) {
  return AUDIO_PATHS[key];
}

export function gameVideoPath(key: GameVideoKey) {
  return VIDEO_PATHS[key];
}
