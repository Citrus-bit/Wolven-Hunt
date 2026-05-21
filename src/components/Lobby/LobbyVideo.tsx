export function LobbyVideo() {
  return (
    <video
      src="/assets/lobby/lobby_pingpong.mp4"
      poster="/assets/lobby/lobby_poster.jpg"
      autoPlay
      muted
      loop
      playsInline
      preload="auto"
      aria-hidden="true"
      className="lobby-video"
    />
  );
}
