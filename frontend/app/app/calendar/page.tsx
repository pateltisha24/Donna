import { Suspense } from "react";
import { CalendarView } from "@/components/app/CalendarView";

export default function CalendarPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full text-sm text-muted-foreground">Loading…</div>}>
      <CalendarView />
    </Suspense>
  );
}
