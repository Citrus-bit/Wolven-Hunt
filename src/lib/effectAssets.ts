export type GameEffectAssetKey =
  | 'guard_shield'
  | 'wolf_attack'
  | 'seer_vision'
  | 'potion_antidote'
  | 'potion_poison'
  | 'out_badge';

const EFFECT_PATHS: Record<GameEffectAssetKey, string> = {
  guard_shield: '/assets/game/effects/guard_shield.png',
  wolf_attack: '/assets/game/effects/wolf_attack.png',
  seer_vision: '/assets/game/effects/seer_vision.png',
  potion_antidote: '/assets/game/effects/potion_antidote.png',
  potion_poison: '/assets/game/effects/potion_poison.png',
  out_badge: '/assets/game/effects/out_badge.png',
};

export function gameEffectAssetPath(key: GameEffectAssetKey) {
  return EFFECT_PATHS[key];
}

export function preloadGameEffectAssets() {
  if (typeof window === 'undefined') {
    return;
  }
  for (const path of Object.values(EFFECT_PATHS)) {
    const image = new Image();
    image.decoding = 'async';
    image.src = path;
  }
}
