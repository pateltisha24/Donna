import { Suspense } from "react";
import { ChatExperience } from "@/components/app/ChatExperience";

export default function AppPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full text-sm text-muted-foreground">Loading…</div>}>
      <ChatExperience />
    </Suspense>
  );
}
