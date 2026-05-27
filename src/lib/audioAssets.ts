export type GameAudioKey =
  | 'wolf_howl'
  | 'night_guard'
  | 'night_wolves'
  | 'night_witch'
  | 'night_seer'
  | 'day_rooster'
  | 'day_dawn'
  | 'day_death'
  | 'day_peaceful'
  | 'speech_seat_1'
  | 'speech_seat_2'
  | 'speech_seat_3'
  | 'speech_seat_4'
  | 'speech_seat_5'
  | 'speech_seat_6'
  | 'speech_seat_7'
  | 'speech_seat_8'
  | 'speech_seat_9'
  | 'speech_seat_10'
  | 'day_vote_start'
  | 'day_last_words_start';

const AUDIO_PATHS: Record<GameAudioKey, string> = {
  wolf_howl: '/assets/game/audio/wolf_howl.mp3',
  night_guard: '/assets/game/audio/night_guard.mp3',
  night_wolves: '/assets/game/audio/night_wolves.mp3',
  night_witch: '/assets/game/audio/night_witch.mp3',
  night_seer: '/assets/game/audio/night_seer.mp3',
  day_rooster: '/assets/game/audio/day_rooster.mp3',
  day_dawn: '/assets/game/audio/day_dawn.mp3',
  day_death: '/assets/game/audio/day_death.mp3',
  day_peaceful: '/assets/game/audio/day_peaceful.mp3',
  speech_seat_1: '/assets/game/audio/speech_seat_1.mp3',
  speech_seat_2: '/assets/game/audio/speech_seat_2.mp3',
  speech_seat_3: '/assets/game/audio/speech_seat_3.mp3',
  speech_seat_4: '/assets/game/audio/speech_seat_4.mp3',
  speech_seat_5: '/assets/game/audio/speech_seat_5.mp3',
  speech_seat_6: '/assets/game/audio/speech_seat_6.mp3',
  speech_seat_7: '/assets/game/audio/speech_seat_7.mp3',
  speech_seat_8: '/assets/game/audio/speech_seat_8.mp3',
  speech_seat_9: '/assets/game/audio/speech_seat_9.mp3',
  speech_seat_10: '/assets/game/audio/speech_seat_10.mp3',
  day_vote_start: '/assets/game/audio/day_vote_start.mp3',
  day_last_words_start: '/assets/game/audio/day_last_words_start.mp3',
};

export function gameAudioPath(key: GameAudioKey) {
  return AUDIO_PATHS[key];
}
