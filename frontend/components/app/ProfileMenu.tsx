"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  ChevronDown,
  Info,
  LogOut,
  Settings as SettingsIcon,
  Sparkles,
  UserCircle2,
} from "lucide-react";
import { Avatar, UserAvatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { clearUserIdCache } from "@/lib/api";

export function ProfileMenu() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [demoMode, setDemoMode] = React.useState(false);

  React.useEffect(() => {
    try {
      setDemoMode(localStorage.getItem("donna_user") === "demo");
    } catch {}
  }, []);

  const isAuthed = status === "authenticated" && !!session?.user;
  const displayName =
    session?.user?.name?.split(" ")[0] || (demoMode ? "Demo" : "Guest");
  const email = session?.user?.email || (demoMode ? "demo@donna.local" : "");
  const initial =
    session?.user?.name?.[0]?.toUpperCase() ||
    session?.user?.email?.[0]?.toUpperCase() ||
    (demoMode ? "D" : "G");
  const image = session?.user?.image || null;

  const handleSignOut = async () => {
    try {
      localStorage.removeItem("donna_user");
    } catch {}
    clearUserIdCache();
    if (isAuthed) {
      // Bring the user back to the landing with the modal forced open.
      await signOut({ callbackUrl: "/" });
    } else {
      // Demo user — clear local marker and bounce to landing modal.
      router.push("/");
    }
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          aria-label="Open profile menu"
          className="group inline-flex items-center gap-1.5 rounded-full p-0.5 pr-1.5 hover:bg-accent transition-colors focus-ring"
        >
          {image ? (
            <Avatar size="sm" className="overflow-hidden p-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={image}
                alt={displayName}
                className="h-full w-full object-cover"
                referrerPolicy="no-referrer"
              />
            </Avatar>
          ) : isAuthed ? (
            <UserAvatar size="sm" initial={initial} />
          ) : (
            <Avatar size="sm" className="bg-accent/60 text-accent-foreground">
              <UserCircle2 className="h-4 w-4" />
            </Avatar>
          )}
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground transition-colors" />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className={cn(
            "z-50 min-w-[220px] rounded-xl border border-border bg-popover p-1.5 shadow-xl",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          )}
        >
          <div className="px-3 py-2 border-b border-border mb-1">
            <p className="text-sm font-medium truncate">{displayName}</p>
            <p className="text-[11px] text-muted-foreground truncate">
              {email || (demoMode ? "Shared demo sandbox" : "Not signed in")}
            </p>
          </div>

          <DropdownMenu.Item asChild>
            <Link
              href="/app/settings"
              className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md text-foreground hover:bg-accent hover:text-accent-foreground cursor-pointer outline-none"
            >
              <SettingsIcon className="h-4 w-4 text-muted-foreground" />
              Settings
            </Link>
          </DropdownMenu.Item>

          <DropdownMenu.Item asChild>
            <Link
              href="/about"
              className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md text-foreground hover:bg-accent hover:text-accent-foreground cursor-pointer outline-none"
            >
              <Info className="h-4 w-4 text-muted-foreground" />
              About
            </Link>
          </DropdownMenu.Item>

          <DropdownMenu.Separator className="my-1 h-px bg-border" />

          {!isAuthed && !demoMode ? (
            <DropdownMenu.Item asChild>
              <Link
                href="/?login=open"
                className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md text-foreground hover:bg-accent hover:text-accent-foreground cursor-pointer outline-none"
              >
                <Sparkles className="h-4 w-4 text-primary" />
                Sign in
              </Link>
            </DropdownMenu.Item>
          ) : (
            <DropdownMenu.Item
              onSelect={handleSignOut}
              className="flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md text-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer outline-none"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </DropdownMenu.Item>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
