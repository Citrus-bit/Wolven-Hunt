import { Check, Plus, X as XIcon } from 'lucide-react';
import { gameEffectAssetPath } from '../../lib/effectAssets';
import type { SeatEffectState } from '../../lib/gameEffects';
import { MODEL_SLOTS } from '../../lib/modelConfigs';
import type { ModelTestStatus } from '../../lib/modelTest';

export type SeatRole = 'wolf' | 'villager' | 'seer' | 'witch' | 'guard';

type GameSeatProps = {
  seatIndex: number;
  side: 'left' | 'right';
  assignment: number | null;
  role?: SeatRole | null;
  testStatus?: ModelTestStatus;
  showTestBadge?: boolean;
  speaking?: boolean;
  dead?: boolean;
  effects?: SeatEffectState;
  disabled?: boolean;
  onClickSeat: (seatIndex: number) => void;
};

export function GameSeat({
  seatIndex,
  side,
  assignment,
  role = null,
  testStatus,
  showTestBadge = true,
  speaking = false,
  dead = false,
  effects,
  disabled = false,
  onClickSeat,
}: GameSeatProps) {
  const isEmpty = assignment === null;
  const slot = isEmpty ? null : MODEL_SLOTS[assignment];
  const isTesting = testStatus === 'testing';
  const showBadge =
    showTestBadge && (testStatus === 'pass' || testStatus === 'fail');
  const resultLabel = testStatus === 'pass' ? '测试通过' : '测试失败';
  const label = slot
    ? `更换 ${slot.nickname}`
    : `添加第 ${seatIndex + 1} 号席位的模型`;
  const showOutBadge = dead || effects?.outBadge;
  const outBadgeKey = effects?.outBadgeSeq ?? (showOutBadge ? 'eliminated' : undefined);

  return (
    <div
      className={[
        'game-seat',
        `game-seat--${side}`,
        speaking ? 'game-seat--speaking' : '',
        dead ? 'game-seat--dead' : '',
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
          disabled={isTesting || disabled}
        >
          {slot ? (
            <img src={slot.iconPath} alt="" className="game-seat-avatar" />
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
      </span>
      <span className="game-seat-nickname">{slot?.nickname ?? ''}</span>
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
