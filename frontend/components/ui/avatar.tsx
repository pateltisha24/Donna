"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "md" | "lg" | "xl";
}

const sizeClasses: Record<NonNullable<AvatarProps["size"]>, string> = {
  sm: "h-7 w-7 text-xs",
  md: "h-9 w-9 text-sm",
  lg: "h-11 w-11 text-base",
  xl: "h-16 w-16 text-xl",
};

export function Avatar({ size = "md", className, ...props }: AvatarProps) {
  return (
    <div
      className={cn(
        "relative inline-flex items-center justify-center rounded-full font-semibold shrink-0",
        sizeClasses[size],
        className
      )}
      {...props}
    />
  );
}

interface DonnaAvatarProps {
  size?: AvatarProps["size"];
  className?: string;
  animated?: boolean;
}

export function DonnaAvatar({ size = "md", className, animated = false }: DonnaAvatarProps) {
  return (
    <Avatar
      size={size}
      className={cn(
        "bg-gradient-to-br from-primary via-[hsl(280_80%_65%)] to-[hsl(252_85%_55%)] text-primary-foreground shadow-md shadow-primary/30",
        animated && "animate-glow",
        className
      )}
    >
      D
    </Avatar>
  );
}

export function UserAvatar({ size = "md", initial = "Y", className }: { size?: AvatarProps["size"]; initial?: string; className?: string }) {
  return (
    <Avatar size={size} className={cn("bg-muted text-muted-foreground border border-border", className)}>
      {initial}
    </Avatar>
  );
}
