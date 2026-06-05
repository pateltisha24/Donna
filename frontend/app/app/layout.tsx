import { Sidebar } from "@/components/app/Sidebar";
import { ChatsProvider } from "@/lib/useChats";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ChatsProvider>
      <div className="flex h-screen overflow-hidden bg-background">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">{children}</div>
      </div>
    </ChatsProvider>
  );
}
