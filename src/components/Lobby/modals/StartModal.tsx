import { LobbyModal } from '../LobbyModal';

type StartModalProps = {
  open: boolean;
  onClose: () => void;
  onEnterGame: () => void;
};

export function StartModal({ open, onClose, onEnterGame }: StartModalProps) {
  const enterGame = () => {
    onClose();
    onEnterGame();
  };

  return (
    <LobbyModal open={open} onClose={onClose} title="开始游戏">
      <p className="lobby-modal-text">
        作者已预填 10 个模型的 API key（自费购买），每月轮换一次。你可以直接开始 AI 对局。
      </p>
      <p className="lobby-modal-tip">
        所有 API key 将会在 2026 年 6 月 19 日过期；如果出现模型无法调用的情况，请联系作者微信：Erammanviimeinen。
      </p>
      <p className="lobby-modal-tip">
        如需长期稳定使用，请进入【设置】→【模型配置】填入你自己的 key；浏览器本地配置优先于默认值。
      </p>
      <div className="lobby-modal-notes" aria-label="注意事项">
        <h3>注意事项</h3>
        <ul>
          <li>当前仍处于测试阶段，部分交互与文案后续可能继续调整。</li>
          <li>建议先确认音量与浏览器权限，进入后体验会更完整。</li>
          <li>局内可以查看完整规则，进入大厅只是开始入口。</li>
        </ul>
      </div>
      <button
        type="button"
        className="lobby-modal-cta"
        onClick={enterGame}
      >
        进入游戏
      </button>
    </LobbyModal>
  );
}
