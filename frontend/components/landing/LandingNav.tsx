"use client";

import * as React from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { ArrowRight, Bot, LogIn, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GithubIcon } from "@/components/ui/icons";
import { LoginModal } from "@/components/auth/LoginModal";

const GITHUB_URL = "https://github.com/pateltisha24/Donna";

/** Reads ?login=open to auto-open the login modal (used by the "Sign in" links). */
function useAutoOpenLogin() {
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    // Read directly from window.location — useSearchParams() can hand back
    // an empty value on first render when the route is statically optimised.
    const url = new URL(window.location.href);
    if (url.searchParams.get("login") === "open") {
      setOpen(true);
      url.searchParams.delete("login");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  return { open, setOpen };
}

export function LandingNav() {
  const { open, setOpen } = useAutoOpenLogin();
  const { data: session, status } = useSession();
  const isAuthed = status === "authenticated" && !!session?.user;

  return (
    <>
      <nav className="flex items-center gap-1">
        <Link href="/about">
          <Button variant="ghost" size="sm">
            How it works
          </Button>
        </Link>
        <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
          <Button variant="ghost" size="icon-sm" aria-label="GitHub">
            <GithubIcon className="h-4 w-4" />
          </Button>
        </a>
        {isAuthed ? (
          <Link href="/app">
            <Button variant="shimmer" size="sm" className="gap-1.5">
              Open app
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        ) : (
          <Button
            variant="shimmer"
            size="sm"
            className="gap-1.5"
            onClick={() => setOpen(true)}
          >
            <LogIn className="h-3.5 w-3.5" />
            Sign in
          </Button>
        )}
      </nav>

      <LoginModal open={open} onOpenChange={setOpen} />
    </>
  );
}

interface CtaProps {
  variant: "hero" | "footer";
}

export function LandingCta({ variant }: CtaProps) {
  const [loginOpen, setLoginOpen] = React.useState(false);
  const { data: session, status } = useSession();
  const isAuthed = status === "authenticated" && !!session?.user;

  const openLogin = () => setLoginOpen(true);

  if (variant === "hero") {
    return (
      <>
        <div className="flex flex-wrap items-center justify-center gap-3 animate-fade-in-up [animation-delay:160ms]">
          {isAuthed ? (
            <Link href="/app">
              <Button size="lg" variant="shimmer" className="gap-2">
                <Bot className="h-4 w-4" />
                Open Donna
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          ) : (
            <Button size="lg" variant="shimmer" className="gap-2" onClick={openLogin}>
              <Bot className="h-4 w-4" />
              Try Donna live
              <ArrowRight className="h-4 w-4" />
            </Button>
          )}
          <Link href="/about">
            <Button size="lg" variant="outline" className="gap-2">
              <Workflow className="h-4 w-4" />
              See how it works
            </Button>
          </Link>
        </div>
        <LoginModal open={loginOpen} onOpenChange={setLoginOpen} />
      </>
    );
  }

  return (
    <>
      {isAuthed ? (
        <Link href="/app">
          <Button size="lg" variant="shimmer" className="gap-2">
            Open Donna
            <ArrowRight className="h-4 w-4" />
          </Button>
        </Link>
      ) : (
        <Button size="lg" variant="shimmer" className="gap-2" onClick={openLogin}>
          Try Donna now
          <ArrowRight className="h-4 w-4" />
        </Button>
      )}
      <LoginModal open={loginOpen} onOpenChange={setLoginOpen} />
    </>
  );
}
