import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Donna — an original, flat-illustration avatar (NOT a likeness of any real
 * person or show character). A poised, professional woman with a bright smile
 * and auburn hair that ties into the app's warm amber palette.
 *
 * Pure SVG so it stays crisp at any size and themes with the brand.
 */
export function DonnaFace({
  size = 112,
  className,
  ring = true,
}: {
  size?: number;
  className?: string;
  ring?: boolean;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 128 128"
      role="img"
      aria-label="Donna"
      className={cn("select-none", className)}
    >
      <defs>
        <clipPath id="donna-clip">
          <circle cx="64" cy="64" r="62" />
        </clipPath>
        <linearGradient id="donna-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(34 80% 90%)" />
          <stop offset="100%" stopColor="hsl(28 70% 80%)" />
        </linearGradient>
        <linearGradient id="donna-hair" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="hsl(20 78% 46%)" />
          <stop offset="100%" stopColor="hsl(14 72% 34%)" />
        </linearGradient>
        <linearGradient id="donna-blazer" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(220 18% 26%)" />
          <stop offset="100%" stopColor="hsl(220 20% 18%)" />
        </linearGradient>
      </defs>

      <g clipPath="url(#donna-clip)">
        {/* Background */}
        <rect x="0" y="0" width="128" height="128" fill="url(#donna-bg)" />

        {/* Hair — back layer behind the head */}
        <path
          d="M64 16
             C40 16 30 34 30 56
             C30 78 36 92 36 92
             L44 84
             C40 72 40 58 42 50
             C58 56 70 56 86 50
             C88 58 88 72 84 84
             L92 92
             C92 92 98 78 98 56
             C98 34 88 16 64 16 Z"
          fill="url(#donna-hair)"
        />

        {/* Shoulders / blazer */}
        <path
          d="M22 128 C22 104 40 94 64 94 C88 94 106 104 106 128 Z"
          fill="url(#donna-blazer)"
        />
        {/* Blouse / collar V */}
        <path d="M54 96 L64 116 L74 96 C71 100 57 100 54 96 Z" fill="hsl(36 40% 92%)" />
        {/* Lapels */}
        <path d="M54 96 L48 122 L57 104 Z" fill="hsl(220 18% 22%)" />
        <path d="M74 96 L80 122 L71 104 Z" fill="hsl(220 18% 22%)" />

        {/* Neck */}
        <path d="M56 84 C56 94 72 94 72 84 L72 96 L56 96 Z" fill="hsl(28 52% 76%)" />
        <path d="M56 84 C56 91 72 91 72 84 L72 89 C72 94 56 94 56 89 Z" fill="hsl(26 46% 70%)" />

        {/* Face */}
        <ellipse cx="64" cy="58" rx="25" ry="28" fill="hsl(30 60% 82%)" />
        {/* Ears */}
        <circle cx="40" cy="60" r="5" fill="hsl(30 60% 82%)" />
        <circle cx="88" cy="60" r="5" fill="hsl(30 60% 82%)" />
        <circle cx="40" cy="64" r="1.6" fill="hsl(44 80% 58%)" />
        <circle cx="88" cy="64" r="1.6" fill="hsl(44 80% 58%)" />

        {/* Hair — front fringe framing the face */}
        <path
          d="M39 56
             C37 40 46 22 64 22
             C82 22 91 40 89 56
             C86 46 80 40 72 39
             C74 43 74 47 73 50
             C66 44 62 44 55 50
             C54 47 54 43 56 39
             C48 40 42 46 39 56 Z"
          fill="url(#donna-hair)"
        />

        {/* Eyebrows */}
        <path d="M50 50 Q56 46 62 49" stroke="hsl(16 60% 30%)" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path d="M66 49 Q72 46 78 50" stroke="hsl(16 60% 30%)" strokeWidth="2" fill="none" strokeLinecap="round" />

        {/* Eyes */}
        <g>
          <ellipse cx="55" cy="57" rx="4.4" ry="5" fill="#fff" />
          <circle cx="55.5" cy="57.5" r="2.6" fill="hsl(24 45% 30%)" />
          <circle cx="55.5" cy="57.5" r="1.1" fill="#1c1410" />
          <circle cx="56.6" cy="56.3" r="0.9" fill="#fff" />
          <ellipse cx="73" cy="57" rx="4.4" ry="5" fill="#fff" />
          <circle cx="72.5" cy="57.5" r="2.6" fill="hsl(24 45% 30%)" />
          <circle cx="72.5" cy="57.5" r="1.1" fill="#1c1410" />
          <circle cx="73.6" cy="56.3" r="0.9" fill="#fff" />
        </g>

        {/* Nose */}
        <path d="M64 60 Q66 66 63 67" stroke="hsl(26 45% 64%)" strokeWidth="1.6" fill="none" strokeLinecap="round" />

        {/* Blush */}
        <ellipse cx="48" cy="66" rx="4.5" ry="2.6" fill="hsl(12 80% 70%)" opacity="0.35" />
        <ellipse cx="80" cy="66" rx="4.5" ry="2.6" fill="hsl(12 80% 70%)" opacity="0.35" />

        {/* Bright smile */}
        <path d="M53 70 Q64 84 75 70 Q64 76 53 70 Z" fill="hsl(8 55% 42%)" />
        <path d="M54.5 70.5 Q64 74 73.5 70.5 Q64 79 54.5 70.5 Z" fill="#fff" />
      </g>

      {ring && (
        <circle
          cx="64"
          cy="64"
          r="62"
          fill="none"
          stroke="hsl(var(--primary) / 0.55)"
          strokeWidth="2"
        />
      )}
    </svg>
  );
}
