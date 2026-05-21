import { LobbyModal } from '../LobbyModal';

type StartModalProps = {
  open: boolean;
  onClose: () => void;
};

export function StartModal({ open, onClose }: StartModalProps) {
  const enterGame = () => {
    console.log('[lobby] enter game');
    onClose();
  };

  return (
    <LobbyModal open={open} onClose={onClose} title="开始游戏">
      <p className="lobby-modal-text">
        尊敬的玩家您好，该游戏目前处于测试版本，所有 api key 均免费开放，请享受游戏吧～
      </p>
      <p className="lobby-modal-tip">
        温馨提示：玩家可以选择人机对战或者 AI 内战，具体游戏规则可在局内查看。
      </p>
      <button type="button" className="lobby-modal-cta" onClick={enterGame}>
        进入游戏
      </button>
    </LobbyModal>
  );
}
