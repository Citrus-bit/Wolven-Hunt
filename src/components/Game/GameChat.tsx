export function GameChat() {
  return (
    <div className="game-chat" aria-label="游戏聊天区">
      <section
        className="game-chat-panel game-chat-panel--general"
        aria-label="通用聊天框"
      >
        <header className="game-chat-header">通用聊天框</header>
        <div className="game-chat-body" role="log" aria-live="polite" />
        <footer className="game-chat-footer">
          <input
            type="text"
            className="game-chat-input"
            placeholder="发言（待接入引擎）"
            disabled
            aria-disabled="true"
          />
        </footer>
      </section>
      <section
        className="game-chat-panel game-chat-panel--wolf"
        aria-label="狼人聊天框"
      >
        <header className="game-chat-header">狼人聊天框</header>
        <div className="game-chat-body" role="log" aria-live="polite" />
        <footer className="game-chat-footer">
          <input
            type="text"
            className="game-chat-input"
            placeholder="狼人夜聊（待接入引擎）"
            disabled
            aria-disabled="true"
          />
        </footer>
      </section>
    </div>
  );
}
