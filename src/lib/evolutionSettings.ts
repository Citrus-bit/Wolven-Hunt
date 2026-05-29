export const PROMPT_EVOLUTION_STORAGE_KEY =
  'wolven_hunt.lobby.prompt_evolution_enabled';

export const PROMPT_EVOLUTION_WARNING =
  '温馨提示：目前的提示词已是最精练版本，如若开启自进化系统可能会出现模型表现不佳的情况，请慎重';

export const booleanLocalStorageSerializer = {
  read: (raw: string): boolean => raw === 'true',
  write: (value: boolean): string => String(value),
};

export function readPromptEvolutionEnabled(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  try {
    return window.localStorage.getItem(PROMPT_EVOLUTION_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

