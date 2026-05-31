import ChatWindow from "./components/ChatWindow";
import NotificationToggle from "./components/NotificationToggle";
import TaskPanel from "./components/TaskPanel";
import ThemeToggle from "./components/ThemeToggle";

export default function Home() {
  return (
    <main className="flex flex-col h-screen" style={{ backgroundColor: "var(--bg)" }}>
      {/* Header */}
      <header
        className="flex items-center justify-between px-6 py-4 border-b"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold"
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-contrast)" }}
          >
            D
          </div>
          <div>
            <h1 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Donna
            </h1>
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Your AI personal secretary
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <TaskPanel />
          <NotificationToggle />
          <ThemeToggle />
        </div>
      </header>

      {/* Chat area */}
      <ChatWindow />
    </main>
  );
}
