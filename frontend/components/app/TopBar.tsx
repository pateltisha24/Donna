"use client";

import * as React from "react";
import { PanelRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ThemeToggle } from "./ThemeToggle";
import { PushToggle } from "./PushToggle";
import { MobileNav } from "./MobileNav";
import { ProfileMenu } from "./ProfileMenu";
import { QuickActions, type QuickAction } from "./QuickActions";

interface TopBarProps {
  onOpenPanel?: () => void;
  onQuickAction?: (action: QuickAction) => void;
  quickDisabled?: boolean;
}

export function TopBar({ onOpenPanel, onQuickAction, quickDisabled }: TopBarProps) {
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
        {onOpenPanel && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onOpenPanel}
                aria-label="Open workspace panel"
              >
                <PanelRight className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Schedule, tasks & insights</TooltipContent>
          </Tooltip>
        )}
        <PushToggle />
        <ThemeToggle />
        <div className="w-px h-5 bg-border mx-1" />
        <ProfileMenu />
      </div>
    </header>
  );
}
