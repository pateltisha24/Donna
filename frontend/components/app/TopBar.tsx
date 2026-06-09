"use client";

import * as React from "react";
import { ThemeToggle } from "./ThemeToggle";
import { PushToggle } from "./PushToggle";
import { MobileNav } from "./MobileNav";
import { ProfileMenu } from "./ProfileMenu";
import { QuickActions, type QuickAction } from "./QuickActions";

interface TopBarProps {
  onQuickAction?: (action: QuickAction) => void;
  quickDisabled?: boolean;
}

export function TopBar({ onQuickAction, quickDisabled }: TopBarProps) {
  return (
    <header className="flex items-center justify-between gap-3 px-3 md:px-4 h-14 border-b border-border bg-card/40 backdrop-blur-xl">
      <div className="flex items-center gap-1 min-w-0 flex-1">
        <MobileNav />
        {onQuickAction && (
          <div className="min-w-0 overflow-x-auto">
            <QuickActions onTrigger={onQuickAction} disabled={quickDisabled} />
          </div>
        )}
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <PushToggle />
        <ThemeToggle />
        <div className="w-px h-5 bg-border mx-1" />
        <ProfileMenu />
      </div>
    </header>
  );
}
