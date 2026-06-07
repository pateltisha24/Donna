"use client";

import * as React from "react";
import Link from "next/link";
import {
  MessageSquare,
  CalendarDays,
  LayoutDashboard,
  LineChart,
  Settings,
  Info,
  Menu,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { DonnaAvatar } from "@/components/ui/avatar";

const NAV = [
  { label: "Today", href: "/app", icon: LayoutDashboard },
  { label: "Chat", href: "/app/chat", icon: MessageSquare },
  { label: "Calendar", href: "/app/calendar", icon: CalendarDays },
  { label: "Productivity", href: "/app/productivity", icon: LineChart },
  { label: "Settings", href: "/app/settings", icon: Settings },
  { label: "About", href: "/about", icon: Info },
];

export function MobileNav() {
  const [open, setOpen] = React.useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open menu">
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 p-0">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-3">
            <DonnaAvatar size="md" />
            <span>Donna</span>
          </SheetTitle>
        </SheetHeader>
        <nav className="p-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
