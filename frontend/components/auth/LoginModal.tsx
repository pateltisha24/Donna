"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { motion } from "framer-motion";
import { UserCircle2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DonnaAvatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Mode = "login" | "register";

interface LoginModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When true, dismiss is restricted to explicit close action — used for sign-out landing. */
  persistent?: boolean;
  initialMode?: Mode;
}

export function LoginModal({
  open,
  onOpenChange,
  persistent = false,
  initialMode = "login",
}: LoginModalProps) {
  const router = useRouter();
  const [mode, setMode] = React.useState<Mode>(initialMode);
  const [busy, setBusy] = React.useState(false);

  // shared
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  // register-only
  const [firstName, setFirstName] = React.useState("");
  const [lastName, setLastName] = React.useState("");

  // Reset to the initial mode whenever the modal is re-opened.
  React.useEffect(() => {
    if (open) setMode(initialMode);
  }, [open, initialMode]);

  const reset = () => {
    setEmail("");
    setPassword("");
    setFirstName("");
    setLastName("");
  };

  const enterDemo = () => {
    setBusy(true);
    try {
      localStorage.setItem("donna_user", "demo");
    } catch {}
    router.push("/app");
  };

  const handleGoogle = async () => {
    setBusy(true);
    try {
      const res = await signIn("google", { callbackUrl: "/app", redirect: false });
      if (res?.error) {
        toast.error("Google sign-in isn't configured.", {
          description: "Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET on the server.",
        });
        setBusy(false);
      } else if (res?.url) {
        window.location.href = res.url;
      } else {
        setBusy(false);
      }
    } catch {
      toast.error("Couldn't start Google sign-in.");
      setBusy(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Enter your email and password.");
      return;
    }
    setBusy(true);
    try {
      const res = await signIn("credentials", {
        email,
        password,
        redirect: false,
        callbackUrl: "/app",
      });
      if (res?.error) {
        toast.error("Incorrect email or password.");
        setBusy(false);
      } else {
        reset();
        router.push("/app");
      }
    } catch {
      toast.error("Couldn't sign you in.");
      setBusy(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firstName.trim()) {
      toast.error("First name is required.");
      return;
    }
    if (password.length < 6) {
      toast.error("Password must be at least 6 characters.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim() || undefined,
          email: email.trim(),
          password,
        }),
      });
      if (!res.ok) {
        let detail = "Couldn't create your account.";
        try {
          const data = await res.json();
          if (data?.detail) detail = data.detail;
        } catch {}
        toast.error(detail);
        setBusy(false);
        return;
      }
      // Auto-sign in after register.
      const signed = await signIn("credentials", {
        email: email.trim(),
        password,
        redirect: false,
        callbackUrl: "/app",
      });
      if (signed?.error) {
        toast.success("Account created. Please sign in.");
        setMode("login");
        setPassword("");
        setBusy(false);
      } else {
        reset();
        router.push("/app");
      }
    } catch {
      toast.error("Couldn't reach the server.");
      setBusy(false);
    }
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setPassword("");
  };

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(o) => {
        if (!o && persistent) return;
        if (!o) reset();
        onOpenChange(o);
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className="fixed inset-0 z-50 bg-background/70 backdrop-blur-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
        />
        <DialogPrimitive.Content
          onOpenAutoFocus={(e) => e.preventDefault()}
          className={cn(
            "fixed left-1/2 top-1/2 z-50 grid w-full max-w-md -translate-x-1/2 -translate-y-1/2",
            "rounded-2xl border border-border bg-card shadow-2xl outline-none",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
            "max-h-[92vh] overflow-y-auto"
          )}
        >
          <motion.div
            key={mode}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="p-6 sm:p-7"
          >
            {!persistent && (
              <DialogPrimitive.Close
                className="absolute right-4 top-4 rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors focus-ring"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </DialogPrimitive.Close>
            )}

            <div className="text-center mb-6">
              <DonnaAvatar size="lg" animated className="mx-auto mb-3" />
              <DialogPrimitive.Title className="text-2xl font-semibold tracking-tight">
                {mode === "login" ? "Welcome back" : "Create your account"}
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="text-sm text-muted-foreground mt-1">
                {mode === "login"
                  ? "Sign in to pick up where you left off."
                  : "Spin up a Donna of your own in 30 seconds."}
              </DialogPrimitive.Description>
            </div>

            {/* Google — always available, top of stack */}
            <GoogleButton onClick={handleGoogle} disabled={busy} />

            <DividerOr label={mode === "login" ? "or sign in with email" : "or use email"} />

            {mode === "login" ? (
              <form onSubmit={handleLogin} className="space-y-3">
                <Field label="Email">
                  <Input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    required
                    disabled={busy}
                  />
                </Field>
                <Field label="Password">
                  <Input
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    required
                    disabled={busy}
                  />
                </Field>
                <Button type="submit" size="lg" className="w-full" disabled={busy}>
                  {busy ? "Signing in…" : "Sign in"}
                </Button>
                <Button
                  type="button"
                  size="lg"
                  variant="outline"
                  className="w-full"
                  onClick={enterDemo}
                  disabled={busy}
                >
                  <UserCircle2 className="h-4 w-4" />
                  Continue as demo user
                </Button>
              </form>
            ) : (
              <form onSubmit={handleRegister} className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="First name">
                    <Input
                      autoComplete="given-name"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      placeholder="First"
                      required
                      disabled={busy}
                    />
                  </Field>
                  <Field label="Last name">
                    <Input
                      autoComplete="family-name"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      placeholder="Last"
                      disabled={busy}
                    />
                  </Field>
                </div>
                <Field label="Email">
                  <Input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    required
                    disabled={busy}
                  />
                </Field>
                <Field label="Password">
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="At least 6 characters"
                    required
                    minLength={6}
                    disabled={busy}
                  />
                </Field>
                <Button type="submit" size="lg" className="w-full" disabled={busy}>
                  {busy ? "Creating account…" : "Create account"}
                </Button>
              </form>
            )}

            <p className="text-[12px] text-center text-muted-foreground mt-5">
              {mode === "login" ? (
                <>
                  Don&apos;t have an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchMode("register")}
                    className="text-primary font-medium hover:underline underline-offset-2"
                  >
                    Create one
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchMode("login")}
                    className="text-primary font-medium hover:underline underline-offset-2"
                  >
                    Log in
                  </button>
                </>
              )}
            </p>
          </motion.div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

// ---------------------------------------------------------------------------

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

function DividerOr({ label }: { label: string }) {
  return (
    <div className="relative my-4">
      <div className="absolute inset-0 flex items-center">
        <span className="w-full border-t border-border" />
      </div>
      <div className="relative flex justify-center text-[10px] uppercase tracking-wider">
        <span className="bg-card px-3 text-muted-foreground">{label}</span>
      </div>
    </div>
  );
}

/** Outline button with the multi-color Google G properly sized (no clipping). */
function GoogleButton({
  onClick,
  disabled,
}: {
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "w-full h-11 rounded-md border border-border bg-card text-sm font-medium text-foreground",
        "inline-flex items-center justify-center gap-3",
        "hover:bg-accent transition-colors focus-ring",
        "disabled:opacity-50 disabled:cursor-not-allowed"
      )}
    >
      <GoogleIcon />
      Continue with Google
    </button>
  );
}

/**
 * Multi-color Google G. viewBox MUST stay at 0 0 48 48 — the paths are drawn
 * in 0–48 coordinates. We pin width/height explicitly so the wrapping button's
 * cva rules can't clamp or clip it.
 */
export function GoogleIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 48 48"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.5-5.9 7.5-11.3 7.5-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.6 5.3 29.6 3 24 3 12.4 3 3 12.4 3 24s9.4 21 21 21 21-9.4 21-21c0-1.2-.1-2.3-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.6 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.6 5.3 29.6 3 24 3 16.3 3 9.7 7.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 45c5.5 0 10.4-2.1 14.2-5.5l-6.6-5.4c-2 1.5-4.6 2.4-7.6 2.4-5.4 0-9.7-3-11.3-7.4L6 33.9C9.4 40.7 16.1 45 24 45z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4-3.9 5.4l6.6 5.4c-.4.3 7-5.1 7-14.8 0-1.2-.1-2.3-.4-3.5z"
      />
    </svg>
  );
}
