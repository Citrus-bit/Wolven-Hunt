import { LobbyModal } from '../LobbyModal';
import { createGame } from '../../../lib/gameApi';
import { useState } from 'react';

type StartModalProps = {
  open: boolean;
  onClose: () => void;
  onEnterGame: (gameId: string) => void;
};

export function StartModal({ open, onClose, onEnterGame }: StartModalProps) {
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enterGame = async () => {
    if (isStarting) {
      return;
    }
    console.log('[lobby] enter game');
    setIsStarting(true);
    setError(null);
    try {
      const { game_id } = await createGame();
      onClose();
      onEnterGame(game_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建游戏失败');
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <LobbyModal open={open} onClose={onClose} title="开始游戏">
      <p className="lobby-modal-text">
        尊敬的玩家您好，该游戏目前处于测试版本，所有 api key 均为作者本人自行购买，免费开放，请享受游戏吧～
      </p>
      <p className="lobby-modal-tip">
        温馨提示：玩家可以选择人机对战或者 AI 内战，具体游戏规则可在局内查看。
      </p>
      <div className="lobby-modal-notes" aria-label="注意事项">
        <h3>注意事项</h3>
        <ul>
          <li>当前仍处于测试阶段，部分交互与文案后续可能继续调整。</li>
          <li>建议先确认音量与浏览器权限，进入后体验会更完整。</li>
          <li>局内可以查看完整规则，进入大厅只是开始入口。</li>
        </ul>
      </div>
      {error && (
        <p className="lobby-modal-tip" role="alert">
          {error}
        </p>
      )}
      <button
        type="button"
        className="lobby-modal-cta"
        onClick={enterGame}
        disabled={isStarting}
      >
        {isStarting ? '正在创建...' : '进入游戏'}
      </button>
    </LobbyModal>
  );
}
