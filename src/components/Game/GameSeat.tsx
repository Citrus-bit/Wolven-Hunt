import { useEffect, useId, useRef, useState } from 'react';
import { Check, Clock3, Plus, X as XIcon } from 'lucide-react';
import { gameEffectAssetPath } from '../../lib/effectAssets';
import type { SeatEffectState } from '../../lib/gameEffects';
import type { HumanRole } from '../../lib/gameApi';
import type { SeatIdentityBadge, SeatRole } from '../../lib/identityMarks';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import type { ModelTestStatus } from '../../lib/modelTest';
import type { SeatPresentation } from '../../lib/seatPresentation';

export type { SeatRole } from '../../lib/identityMarks';

type GameSeatProps = {
  seatIndex: number;
  side: 'left' | 'right';
  assignment: number | null;
  presentation?: SeatPresentation | null;
  role?: SeatRole | null;
  identityBadge?: SeatIdentityBadge | null;
  identityMarkEnabled?: boolean;
  identityMarkValue?: SeatRole | null;
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
  privateWolfAttackCue?: boolean;
  witchSplit?: {
    active: boolean;
    canSave: boolean;
    canPoison: boolean;
    onSave: () => void;
    onPoison: () => void;
  };
  onPickHumanRole?: (role: HumanRole) => void;
  onPickIdentityMark?: (seatIndex: number, role: SeatRole | null) => void;
  onClickSeat: (seatIndex: number) => void;
};

export function GameSeat({
  seatIndex,
  side,
  assignment,
  presentation = null,
  role = null,
  identityBadge = null,
  identityMarkEnabled = false,
  identityMarkValue = null,
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
  privateWolfAttackCue = false,
  witchSplit,
  onPickHumanRole,
  onPickIdentityMark,
  onClickSeat,
}: GameSeatProps) {
  const roleMenuId = useId();
  const identityMenuId = useId();
  const [roleMenuOpen, setRoleMenuOpen] = useState(false);
  const [identityMenuOpen, setIdentityMenuOpen] = useState(false);
  const rolePickerRef = useRef<HTMLSpanElement | null>(null);
  const identityPickerRef = useRef<HTMLSpanElement | null>(null);
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
      : identityMarkEnabled
      ? `标注 ${seatIndex + 1}号 ${display.nickname} 的可能身份`
      : disabled
      ? `${seatIndex + 1}号席位 ${display.nickname}`
      : `更换 ${display.nickname}`
    : `添加第 ${seatIndex + 1} 号席位的模型`;
  const showOutBadge = dead || effects?.outBadge;
  const outBadgeKey = effects?.outBadgeSeq ?? (showOutBadge ? 'eliminated' : undefined);
  const selectedHumanRole =
    HUMAN_ROLE_OPTIONS.find((option) => option.role === humanRole) ?? HUMAN_ROLE_OPTIONS[0];
  const visibleIdentityBadge = identityBadge ?? (role ? toTrueRoleBadge(role) : null);
  const identityMarkLabel = identityMarkValue
    ? ROLE_LABELS[identityMarkValue]
    : '未标注';
  const handleSeatClick = () => {
    if (identityMarkEnabled) {
      setIdentityMenuOpen(!identityMenuOpen);
      return;
    }
    onClickSeat(seatIndex);
  };

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

  useEffect(() => {
    if (!identityMenuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && identityPickerRef.current?.contains(target)) {
        return;
      }
      setIdentityMenuOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIdentityMenuOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [identityMenuOpen]);

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
          onClick={handleSeatClick}
          disabled={isTesting || (disabled && !targetable && !identityMarkEnabled)}
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
        {visibleIdentityBadge && (
          <span
            className={identityBadgeClassName(visibleIdentityBadge)}
            aria-label={identityBadgeAriaLabel(visibleIdentityBadge)}
            title={identityBadgeAriaLabel(visibleIdentityBadge)}
          >
            {identityBadgeText(visibleIdentityBadge)}
          </span>
        )}
        {identityMarkEnabled && (
          <span
            className="game-seat-identity-picker"
            ref={identityPickerRef}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="game-seat-identity-picker-button"
              aria-label={`${seatIndex + 1}号身份标注，当前${identityMarkLabel}`}
              aria-haspopup="listbox"
              aria-expanded={identityMenuOpen}
              aria-controls={identityMenuOpen ? identityMenuId : undefined}
              title={`${seatIndex + 1}号身份标注：${identityMarkLabel}`}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => setIdentityMenuOpen((open) => !open)}
            >
              <span>{identityMarkValue ? ROLE_SHORT_LABELS[identityMarkValue] : '标'}</span>
              <span className="game-seat-role-picker-caret" aria-hidden="true" />
            </button>
            {identityMenuOpen && (
              <span
                id={identityMenuId}
                className="game-seat-role-menu game-seat-identity-menu"
                role="listbox"
                aria-label={`${seatIndex + 1}号可能身份`}
              >
                {IDENTITY_MARK_OPTIONS.map((option) => {
                  const selected = option.role === identityMarkValue;
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
                        onPickIdentityMark?.(seatIndex, option.role);
                        setIdentityMenuOpen(false);
                      }}
                    >
                      <span>{option.label}</span>
                      {selected && <Check size={12} strokeWidth={3} aria-hidden="true" />}
                    </button>
                  );
                })}
                <button
                  type="button"
                  role="option"
                  aria-selected={identityMarkValue === null}
                  className={[
                    'game-seat-role-option',
                    'game-seat-role-option--clear',
                    identityMarkValue === null ? 'game-seat-role-option--selected' : '',
                  ].join(' ')}
                  onClick={() => {
                    onPickIdentityMark?.(seatIndex, null);
                    setIdentityMenuOpen(false);
                  }}
                >
                  清除
                </button>
              </span>
            )}
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
          {privateWolfAttackCue && !effects?.wolfAttack && (
            <img
              key={`private-wolf-attack-${seatIndex}`}
              src={gameEffectAssetPath('wolf_attack')}
              alt=""
              className="game-seat-effect game-seat-effect--wolf game-seat-effect--private-wolf-cue"
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

const ROLE_SHORT_LABELS: Record<SeatRole, string> = {
  wolf: '狼',
  villager: '民',
  seer: '预',
  witch: '巫',
  guard: '守',
};

const HUMAN_ROLE_OPTIONS: { role: HumanRole; label: string; shortLabel: string }[] = [
  { role: 'random', label: '随机', shortLabel: '随机' },
  { role: 'villager', label: '平民', shortLabel: '民' },
  { role: 'witch', label: '女巫', shortLabel: '巫' },
  { role: 'seer', label: '预言家', shortLabel: '预' },
  { role: 'guard', label: '守卫', shortLabel: '守' },
  { role: 'wolf', label: '狼人', shortLabel: '狼' },
];

const IDENTITY_MARK_OPTIONS: { role: SeatRole; label: string }[] = [
  { role: 'wolf', label: '狼人' },
  { role: 'villager', label: '村民' },
  { role: 'seer', label: '预言家' },
  { role: 'witch', label: '女巫' },
  { role: 'guard', label: '守卫' },
];

function toTrueRoleBadge(role: SeatRole): SeatIdentityBadge {
  return { kind: 'role', role, source: 'true' };
}

function identityBadgeClassName(badge: SeatIdentityBadge) {
  if (badge.kind === 'camp') {
    return [
      'game-seat-role',
      'game-seat-role--camp',
      `game-seat-role--camp-${badge.camp}`,
      'game-seat-role--locked',
    ].join(' ');
  }
  return [
    'game-seat-role',
    `game-seat-role--${badge.role}`,
    badge.source === 'guess' ? 'game-seat-role--guess' : '',
  ].join(' ');
}

function identityBadgeText(badge: SeatIdentityBadge) {
  if (badge.kind === 'camp') {
    return badge.camp === 'wolf' ? '狼人' : '好人';
  }
  return ROLE_BADGES[badge.role];
}

function identityBadgeAriaLabel(badge: SeatIdentityBadge) {
  if (badge.kind === 'camp') {
    return `预言家查验锁定阵营：${badge.camp === 'wolf' ? '狼人阵营' : '好人阵营'}`;
  }
  if (badge.source === 'guess') {
    return `可能身份：${ROLE_LABELS[badge.role]}`;
  }
  return `身份：${ROLE_LABELS[badge.role]}`;
}
