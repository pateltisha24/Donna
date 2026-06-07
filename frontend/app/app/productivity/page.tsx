import { Suspense } from "react";
import { ProductivityView } from "@/components/app/ProductivityView";

export default function ProductivityPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full text-sm text-muted-foreground">Loading…</div>}>
      <ProductivityView />
    </Suspense>
  );
}
