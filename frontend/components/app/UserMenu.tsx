"use client";

import * as React from "react";
import Link from "next/link";
import { useSession, signOut } from "next-auth/react";
import { LogIn, LogOut, UserCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UserAvatar } from "@/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function UserMenu() {
  const { data: session, status } = useSession();
  const [demoMode, setDemoMode] = React.useState(false);

  React.useEffect(() => {
    try {
      setDemoMode(localStorage.getItem("donna_user") === "demo");
    } catch {}
  }, []);

  if (status === "loading") {
    return <div className="h-8 w-8" aria-hidden />;
  }

  // Authenticated via Google
  if (session?.user) {
    const initial =
      session.user.name?.[0]?.toUpperCase() ||
      session.user.email?.[0]?.toUpperCase() ||
      "U";
    return (
      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <UserAvatar
              size="sm"
              initial={initial}
              className="bg-primary/20 text-primary border-primary/30"
            />
          </TooltipTrigger>
          <TooltipContent side="bottom">{session.user.email}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Sign out"
              onClick={() => signOut({ callbackUrl: "/" })}
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Sign out</TooltipContent>
        </Tooltip>
      </div>
    );
  }

  // Demo mode
  if (demoMode) {
    return (
      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-accent/50 text-accent-foreground text-[10px] font-medium">
              <UserCircle2 className="h-3 w-3" />
              Demo
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom">You&apos;re in the shared demo sandbox</TooltipContent>
        </Tooltip>
        <Link href="/login">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <LogIn className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Sign in</span>
          </Button>
        </Link>
      </div>
    );
  }

  // Not signed in & not in demo — invite to login
  return (
    <Link href="/login">
      <Button variant="ghost" size="sm" className="gap-1.5">
        <LogIn className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Sign in</span>
      </Button>
    </Link>
  );
}
