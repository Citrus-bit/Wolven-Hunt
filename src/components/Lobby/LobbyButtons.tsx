export type LobbyAction = 'start' | 'history' | 'settings';

type LobbyButtonItem = {
  kind: LobbyAction;
  label: string;
  src: string;
};

type LobbyButtonsProps = {
  onAction?: (kind: LobbyAction) => void;
};

const buttons: LobbyButtonItem[] = [
  {
    kind: 'start',
    label: '开始游戏',
    src: '/assets/lobby/btn_start.png',
  },
  {
    kind: 'history',
    label: '历史复盘',
    src: '/assets/lobby/btn_history.png',
  },
  {
    kind: 'settings',
    label: '系统设置',
    src: '/assets/lobby/btn_settings.png',
  },
];

export function LobbyButtons({ onAction }: LobbyButtonsProps) {
  return (
    <div className="lobby-buttons" aria-label="大厅操作">
      {buttons.map((button) => (
        <button
          key={button.kind}
          type="button"
          aria-label={button.label}
          className="lobby-btn"
          onClick={() => {
            console.log(`[lobby] click: ${button.kind}`);
            onAction?.(button.kind);
          }}
        >
          <img src={button.src} alt={button.label} draggable="false" />
        </button>
      ))}
    </div>
  );
}
