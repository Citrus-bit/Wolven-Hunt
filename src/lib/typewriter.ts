export const TYPEWRITER_DURATION_MS = 1600;

export type TypewriterTextOptions = {
  elapsedMs: number;
  durationMs?: number;
  enabled?: boolean;
  reducedMotion?: boolean;
};

export function typewriterVisibleLength(
  text: string,
  {
    elapsedMs,
    durationMs = TYPEWRITER_DURATION_MS,
    enabled = true,
    reducedMotion = false,
  }: TypewriterTextOptions,
) {
  const units = Array.from(text);
  if (!enabled || reducedMotion || units.length === 0 || durationMs <= 0) {
    return units.length;
  }
  const progress = clamp(elapsedMs / durationMs, 0, 1);
  return Math.min(units.length, Math.ceil(units.length * progress));
}

export function typewriterVisibleText(
  text: string,
  options: TypewriterTextOptions,
) {
  const visibleLength = typewriterVisibleLength(text, options);
  return Array.from(text).slice(0, visibleLength).join('');
}

export function isTypewriterComplete(
  text: string,
  options: TypewriterTextOptions,
) {
  return typewriterVisibleLength(text, options) >= Array.from(text).length;
}

function clamp(value: number, min: number, max: number) {
  if (Number.isNaN(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}
