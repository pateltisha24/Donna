import ChatWindow from "./components/ChatWindow";

export default function Home() {
  return (
    <main className="flex flex-col h-screen" style={{ backgroundColor: "#0f0f11" }}>
      {/* Header */}
      <header
        className="flex items-center px-6 py-4 border-b"
        style={{ borderColor: "#2a2a33", backgroundColor: "#1a1a1f" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold"
            style={{ backgroundColor: "#7c6af7", color: "#fff" }}
          >
            D
          </div>
          <div>
            <h1 className="text-sm font-semibold" style={{ color: "#e8e8f0" }}>
              Donna
            </h1>
            <p className="text-xs" style={{ color: "#8888a0" }}>
              Your AI personal secretary
            </p>
          </div>
        </div>
      </header>

      {/* Chat area */}
      <ChatWindow />
    </main>
  );
}
