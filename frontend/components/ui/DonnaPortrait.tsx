"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { DonnaFace } from "./DonnaFace";

/**
 * Donna's brand portrait. Uses the illustrated PNG at `public/donna-avatar.png`
 * and gracefully falls back to the hand-built SVG face if that file isn't
 * present yet — so the UI never shows a broken image.
 *
 * Drop the artwork at: frontend/public/donna-avatar.png
 */
export function DonnaPortrait({
  size = 120,
  className,
  ring = true,
  src = "/donna-avatar.png",
}: {
  size?: number;
  className?: string;
  ring?: boolean;
  src?: string;
}) {
  // Preload the artwork: only swap to it once it actually decodes. Until then
  // (or if the file is missing) we render the SVG face — no broken-image flash,
  // and it works the instant the PNG is dropped into public/.
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    let active = true;
    const img = new window.Image();
    img.onload = () => active && setReady(true);
    img.onerror = () => active && setReady(false);
    img.src = src;
    return () => {
      active = false;
    };
  }, [src]);

  if (!ready) {
    return <DonnaFace size={size} className={className} ring={ring} />;
  }

  return (
    <div
      className={cn(
        "relative rounded-full overflow-hidden bg-[hsl(36_36%_94%)]",
        ring && "ring-2 ring-primary/55",
        className
      )}
      style={{ width: size, height: size }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt="Donna"
        width={size}
        height={size}
        draggable={false}
        className="h-full w-full object-cover object-top"
      />
    </div>
  );
}
