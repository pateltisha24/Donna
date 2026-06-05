"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  BarChart3,
  Calendar,
  CheckSquare,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DonnaAvatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { useChats } from "@/lib/useChats";

const TOOL_NAV = [
  { label: "Schedule", href: "/app?panel=schedule", icon: Calendar },
  { label: "Tasks", href: "/app?panel=tasks", icon: CheckSquare },
  { label: "Insights", href: "/app?panel=insights", icon: BarChart3 },
  { label: "Emergency Replan", href: "/app?action=emergency", icon: Zap },
] as const;

export function Sidebar({ className }: { className?: string }) {
  return (
    <aside
      className={cn(
        "hidden md:flex flex-col w-[272px] shrink-0 border-r border-border bg-card/40 backdrop-blur-xl",
        className
      )}
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
        <DonnaAvatar size="md" />
        <div className="flex flex-col min-w-0">
          <span className="text-sm font-semibold tracking-tight">Donna</span>
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Sparkles className="h-3 w-3" /> AI Chief of Staff
          </span>
        </div>
      </div>

      {/* New chat button */}
      <NewChatButton />

      {/* Chats list (takes the bulk of the sidebar) */}
      <ChatList />

      {/* Tools — sits at the bottom of the sidebar */}
      <nav className="px-3 py-3 border-t border-border">
        <ul className="space-y-0.5">
          {TOOL_NAV.map((item) => (
            <ToolLink key={item.label} {...item} />
          ))}
        </ul>
      </nav>
    </aside>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
    </p>
  );
}

function ToolLink({
  label,
  href,
  icon: Icon,
}: {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  const pathname = usePathname();
  const active = pathname === href.split("?")[0];
  return (
    <li>
      <Link
        href={href}
        className={cn(
          "flex items-center gap-3 px-3 py-1.5 rounded-md text-sm transition-colors",
          active
            ? "bg-accent/70 text-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-accent/40"
        )}
      >
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground/80" />
        <span className="truncate">{label}</span>
      </Link>
    </li>
  );
}

// ---------------------------------------------------------------------------
// New chat
// ---------------------------------------------------------------------------

function NewChatButton() {
  const router = useRouter();
  const { newChat } = useChats();
  const [busy, setBusy] = React.useState(false);

  const handle = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await newChat();
      router.push("/app");
    } catch (e) {
      console.error(e);
      toast.error("Couldn't start a new chat.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-3 py-3 border-b border-border">
      <Button
        onClick={handle}
        disabled={busy}
        variant="outline"
        className="w-full justify-start gap-2 h-9"
      >
        <Plus className="h-4 w-4" />
        New chat
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat list
// ---------------------------------------------------------------------------

function ChatList() {
  const { chats, activeId, setActiveId, loading } = useChats();
  const router = useRouter();
  const pathname = usePathname();

  const select = (id: string) => {
    setActiveId(id);
    if (pathname !== "/app") router.push("/app");
  };

  return (
    <div className="flex-1 overflow-y-auto px-2 py-2 min-h-0">
      <SectionLabel>Chats</SectionLabel>
      {loading && chats.length === 0 ? (
        <p className="px-3 py-4 text-xs text-muted-foreground">Loading…</p>
      ) : chats.length === 0 ? (
        <p className="px-3 py-4 text-xs text-muted-foreground leading-relaxed">
          No chats yet. Start one to see it here.
        </p>
      ) : (
        <ul className="space-y-0.5">
          {chats.map((c) => (
            <ChatRow
              key={c.id}
              id={c.id}
              title={c.title}
              active={c.id === activeId && pathname === "/app"}
              onSelect={() => select(c.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ChatRow({
  id,
  title,
  active,
  onSelect,
}: {
  id: string;
  title: string;
  active: boolean;
  onSelect: () => void;
}) {
  const { rename, remove } = useChats();
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(title);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Keep the draft synced when the title prop changes (e.g. AI auto-title).
  React.useEffect(() => {
    if (!editing) setDraft(title);
  }, [title, editing]);

  const startEdit = React.useCallback(() => {
    setDraft(title);
    setEditing(true);
    // Defer focus to next tick so the input has actually mounted.
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.select();
      }
    });
  }, [title]);

  const cancelEdit = React.useCallback(() => {
    setDraft(title);
    setEditing(false);
  }, [title]);

  const commitRename = React.useCallback(async () => {
    const next = draft.trim().slice(0, 80);
    setEditing(false);
    if (!next || next === title) {
      setDraft(title);
      return;
    }
    try {
      await rename(id, next);
    } catch {
      setDraft(title);
      toast.error("Couldn't rename chat.");
    }
  }, [draft, id, rename, title]);

  const handleDelete = async () => {
    try {
      await remove(id);
    } catch {
      toast.error("Couldn't delete chat.");
    }
  };

  return (
    <li>
      <div
        className={cn(
          "group flex items-center gap-0.5 rounded-md pr-1 transition-colors",
          active
            ? "bg-accent text-accent-foreground"
            : "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
        )}
      >
        {editing ? (
          <div className="flex-1 min-w-0 flex items-center gap-2.5 pl-3 pr-1 py-0.5">
            <MessageSquare className="h-3.5 w-3.5 shrink-0 text-primary" />
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitRename();
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  cancelEdit();
                }
              }}
              className="flex-1 min-w-0 bg-background/60 rounded px-2 py-1 text-sm outline-none border border-primary/60 ring-2 ring-primary/15 text-foreground"
              maxLength={80}
              aria-label="Rename chat"
            />
          </div>
        ) : (
          <button
            onClick={onSelect}
            onDoubleClick={startEdit}
            className="flex-1 min-w-0 flex items-center gap-2.5 px-3 py-1.5 text-left"
            title={`${title}  ·  double-click to rename`}
          >
            <MessageSquare
              className={cn(
                "h-3.5 w-3.5 shrink-0 transition-colors",
                active ? "text-primary" : "text-muted-foreground"
              )}
            />
            <span className="truncate text-sm">{title}</span>
          </button>
        )}

        {!editing && (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                aria-label="Chat options"
                onClick={(e) => e.stopPropagation()}
                className={cn(
                  "shrink-0 p-1 rounded text-muted-foreground hover:text-foreground hover:bg-background/60 transition-all",
                  active
                    ? "opacity-100"
                    : "opacity-0 group-hover:opacity-100 focus:opacity-100"
                )}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={4}
                className={cn(
                  "z-50 min-w-[160px] rounded-lg border border-border bg-popover p-1 shadow-xl",
                  "data-[state=open]:animate-in data-[state=closed]:animate-out",
                  "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                  "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
                )}
              >
                <DropdownMenu.Item
                  // Close the menu, THEN switch to inline edit on the next frame
                  // so the menu's focus return doesn't steal the input focus.
                  onSelect={() => {
                    requestAnimationFrame(startEdit);
                  }}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-md cursor-pointer outline-none hover:bg-accent"
                >
                  <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                  Rename
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  onSelect={handleDelete}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-md cursor-pointer outline-none hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        )}
      </div>
    </li>
  );
}
