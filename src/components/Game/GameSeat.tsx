import { useEffect, useId, useRef, useState } from 'react';
import { Check, Clock3, Plus, X as XIcon } from 'lucide-react';
import { gameEffectAssetPath } from '../../lib/effectAssets';
import type { SeatEffectState } from '../../lib/gameEffects';
import type { HumanRole } from '../../lib/gameApi';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import type { ModelTestStatus } from '../../lib/modelTest';
import type { SeatPresentation } from '../../lib/seatPresentation';

export type SeatRole = 'wolf' | 'villager' | 'seer' | 'witch' | 'guard';

type GameSeatProps = {
  seatIndex: number;
  side: 'left' | 'right';
  assignment: number | null;
  presentation?: SeatPresentation | null;
  role?: SeatRole | null;
  testStatus?: ModelTestStatus;
  showTestBadge?: boolean;
  thinkingEnabled?: boolean;
  speaking?: boolean;
  dead?: boolean;
  effects?: SeatEffectState;
  disabled?: boolean;
  isHuman?: boolean;
  humanRole?: HumanRole;
  pickRoleEnabled?: boolean;
  targetable?: boolean;
  selectedAsTarget?: boolean;
  witchSplit?: {
    active: boolean;
    canSave: boolean;
    canPoison: boolean;
    onSave: () => void;
    onPoison: () => void;
  };
  onPickHumanRole?: (role: HumanRole) => void;
  onClickSeat: (seatIndex: number) => void;
};

export function GameSeat({
  seatIndex,
  side,
  assignment,
  presentation = null,
  role = null,
  testStatus,
  showTestBadge = true,
  thinkingEnabled = false,
  speaking = false,
  dead = false,
  effects,
  disabled = false,
  isHuman = false,
  humanRole = 'random',
  pickRoleEnabled = false,
  targetable = false,
  selectedAsTarget = false,
  witchSplit,
  onPickHumanRole,
  onClickSeat,
}: GameSeatProps) {
  const roleMenuId = useId();
  const [roleMenuOpen, setRoleMenuOpen] = useState(false);
  const rolePickerRef = useRef<HTMLSpanElement | null>(null);
  const slot = assignment === null ? null : MODEL_SLOTS[assignment];
  const display = slot
    ? { nickname: slot.nickname, iconPath: slot.iconPath }
    : presentation
      ? { nickname: presentation.nickname, iconPath: presentation.icon_path }
      : disabled
        ? { nickname: `${seatIndex + 1}号`, iconPath: '' }
        : null;
  const isTesting = testStatus === 'testing';
  const showBadge =
    showTestBadge && (testStatus === 'pass' || testStatus === 'fail');
  const resultLabel = testStatus === 'pass' ? '测试通过' : '测试失败';
  const label = display
    ? targetable
      ? `选择 ${seatIndex + 1}号 ${display.nickname}`
      : disabled
      ? `${seatIndex + 1}号席位 ${display.nickname}`
      : `更换 ${display.nickname}`
    : `添加第 ${seatIndex + 1} 号席位的模型`;
  const showOutBadge = dead || effects?.outBadge;
  const outBadgeKey = effects?.outBadgeSeq ?? (showOutBadge ? 'eliminated' : undefined);
  const selectedHumanRole =
    HUMAN_ROLE_OPTIONS.find((option) => option.role === humanRole) ?? HUMAN_ROLE_OPTIONS[0];

  useEffect(() => {
    if (!roleMenuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && rolePickerRef.current?.contains(target)) {
        return;
      }
      setRoleMenuOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setRoleMenuOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [roleMenuOpen]);

  return (
    <div
      className={[
        'game-seat',
        `game-seat--${side}`,
        speaking ? 'game-seat--speaking' : '',
        dead ? 'game-seat--dead' : '',
        isHuman ? 'game-seat--human' : '',
        targetable ? 'game-seat--targetable' : '',
        selectedAsTarget ? 'game-seat--selected-target' : '',
      ].join(' ')}
      data-seat-index={seatIndex}
    >
      <span className="game-seat-visual">
        <button
          type="button"
          className={`game-seat-circle ${
            isTesting ? 'game-seat-circle--testing' : ''
          }`}
          aria-label={label}
          onClick={() => onClickSeat(seatIndex)}
          disabled={isTesting || (disabled && !targetable)}
        >
          {display?.iconPath ? (
            <img src={display.iconPath} alt="" className="game-seat-avatar" />
          ) : disabled ? (
            <span className="game-seat-placeholder-avatar" aria-hidden="true">
              {seatIndex + 1}号
            </span>
          ) : (
            <Plus aria-hidden="true" size={36} strokeWidth={2.5} />
          )}
          {isTesting && (
            <span className="game-seat-dots" aria-hidden="true">
              <span className="dot dot-1" />
              <span className="dot dot-2" />
              <span className="dot dot-3" />
            </span>
          )}
        </button>
        <span className="game-seat-number">{seatIndex + 1}</span>
        {role && (
          <span
            className={`game-seat-role game-seat-role--${role}`}
            aria-label={`身份：${ROLE_LABELS[role]}`}
          >
            {ROLE_BADGES[role]}
          </span>
        )}
        {isHuman && pickRoleEnabled && (
          <span
            className="game-seat-role-picker"
            ref={rolePickerRef}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="game-seat-role-picker-button"
              aria-label={`选择你的角色，当前${selectedHumanRole.label}`}
              aria-haspopup="listbox"
              aria-expanded={roleMenuOpen}
              aria-controls={roleMenuOpen ? roleMenuId : undefined}
              title={`选择你的角色：${selectedHumanRole.label}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => setRoleMenuOpen((open) => !open)}
            >
              <span>{selectedHumanRole.shortLabel}</span>
              <span className="game-seat-role-picker-caret" aria-hidden="true" />
            </button>
            {roleMenuOpen && (
              <span
                id={roleMenuId}
                className="game-seat-role-menu"
                role="listbox"
                aria-label="选择你的角色"
              >
                {HUMAN_ROLE_OPTIONS.map((option) => {
                  const selected = option.role === humanRole;
                  return (
                    <button
                      key={option.role}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={[
                        'game-seat-role-option',
                        selected ? 'game-seat-role-option--selected' : '',
                      ].join(' ')}
                      onClick={() => {
                        onPickHumanRole?.(option.role);
                        setRoleMenuOpen(false);
                      }}
                    >
                      <span>{option.label}</span>
                      {selected && <Check size={12} strokeWidth={3} aria-hidden="true" />}
                    </button>
                  );
                })}
              </span>
            )}
          </span>
        )}
        {witchSplit?.active && (
          <span className="game-seat-witch-split" aria-label={`${seatIndex + 1}号女巫操作`}>
            <button
              type="button"
              className="game-seat-witch-half game-seat-witch-half--save"
              disabled={!witchSplit.canSave}
              onClick={witchSplit.onSave}
            >
              救
            </button>
            <button
              type="button"
              className="game-seat-witch-half game-seat-witch-half--poison"
              disabled={!witchSplit.canPoison}
              onClick={witchSplit.onPoison}
            >
              毒
            </button>
          </span>
        )}
        <span className="game-seat-effect-slot" aria-hidden="true">
          {effects?.guardShield && (
            <img
              key={effects.guardShieldSeq}
              src={gameEffectAssetPath('guard_shield')}
              alt=""
              className="game-seat-effect game-seat-effect--guard"
            />
          )}
          {effects?.wolfAttack && (
            <img
              key={effects.wolfAttackSeq}
              src={gameEffectAssetPath('wolf_attack')}
              alt=""
              className={[
                'game-seat-effect',
                'game-seat-effect--wolf',
                effects.wolfAttackBlocked ? 'game-seat-effect--blocked' : '',
              ].join(' ')}
            />
          )}
          {effects?.seerVisionSeq && (
            <img
              key={effects.seerVisionSeq}
              src={gameEffectAssetPath('seer_vision')}
              alt=""
              className="game-seat-effect game-seat-effect--seer"
            />
          )}
          {showOutBadge && (
            <img
              key={outBadgeKey}
              src={gameEffectAssetPath('out_badge')}
              alt=""
              className="game-seat-effect game-seat-effect--out"
            />
          )}
        </span>
        {showBadge && (
          <span
            className={`game-seat-badge game-seat-badge--${testStatus}`}
            aria-label={resultLabel}
          >
            {testStatus === 'pass' ? (
              <Check size={16} strokeWidth={3} aria-hidden="true" />
            ) : (
              <XIcon size={16} strokeWidth={3} aria-hidden="true" />
            )}
          </span>
        )}
        {thinkingEnabled && (
          <span
            className="game-seat-thinking-badge"
            aria-label="思考模式开启，响应更慢"
            title="思考模式开启，响应更慢"
          >
            <Clock3 size={14} strokeWidth={3} aria-hidden="true" />
          </span>
        )}
      </span>
      <span className="game-seat-nickname">{display?.nickname ?? ''}</span>
    </div>
  );
}

const ROLE_LABELS: Record<SeatRole, string> = {
  wolf: '狼人',
  villager: '村民',
  seer: '预言家',
  witch: '女巫',
  guard: '守卫',
};

const ROLE_BADGES: Record<SeatRole, string> = {
  wolf: '狼人',
  villager: '村民',
  seer: '预言',
  witch: '女巫',
  guard: '守卫',
};

const HUMAN_ROLE_OPTIONS: { role: HumanRole; label: string; shortLabel: string }[] = [
  { role: 'random', label: '随机', shortLabel: '随机' },
  { role: 'villager', label: '平民', shortLabel: '民' },
  { role: 'witch', label: '女巫', shortLabel: '巫' },
  { role: 'seer', label: '预言家', shortLabel: '预' },
  { role: 'guard', label: '守卫', shortLabel: '守' },
  { role: 'wolf', label: '狼人', shortLabel: '狼' },
];
