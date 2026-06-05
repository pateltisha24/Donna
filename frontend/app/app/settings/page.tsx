"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import { toast } from "sonner";
import {
  Bell,
  ChevronLeft,
  Clock,
  LogOut,
  Mail,
  Palette,
  Sparkles,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TopBar } from "@/components/app/TopBar";
import { getMe, updateSettings, type UserProfile } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const { data: session } = useSession();

  const [profile, setProfile] = React.useState<UserProfile | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);

  // local form state
  const [name, setName] = React.useState("");
  const [workingStyle, setWorkingStyle] = React.useState("");
  const [wake, setWake] = React.useState("08:00");
  const [eod, setEod] = React.useState("21:00");

  const [theme, setTheme] = React.useState<"dark" | "light">("dark");

  React.useEffect(() => {
    setLoading(true);
    getMe()
      .then(({ profile }) => {
        setProfile(profile);
        setName(profile.name || session?.user?.name || "");
        setWorkingStyle(profile.working_style || "");
        setWake(profile.wake_time || "08:00");
        setEod(profile.eod_time || "21:00");
      })
      .catch(() => setProfile(null))
      .finally(() => setLoading(false));

    try {
      const saved = (localStorage.getItem("donna_theme") as "dark" | "light") || "dark";
      setTheme(saved);
    } catch {}
  }, [session?.user?.name]);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await updateSettings({
        name: name.trim() || undefined,
        working_style: workingStyle.trim() || undefined,
        wake_time: wake,
        eod_time: eod,
      });
      if (updated) {
        setProfile(updated);
        toast.success("Settings saved.");
      } else {
        toast.message("Nothing to save.");
      }
    } catch {
      toast.error("Couldn't save settings.");
    } finally {
      setSaving(false);
    }
  };

  const applyTheme = (next: "dark" | "light") => {
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("donna_theme", next);
    } catch {}
  };

  const handleSignOut = async () => {
    try {
      localStorage.removeItem("donna_user");
    } catch {}
    if (session?.user) {
      await signOut({ callbackUrl: "/" });
    } else {
      router.push("/");
    }
  };

  const email = session?.user?.email || "demo@donna.local";
  const isAuthed = !!session?.user;

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar />

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto w-full px-4 md:px-6 py-8">
          <button
            onClick={() => router.back()}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-6"
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </button>

          <h1 className="text-2xl font-semibold tracking-tight mb-1">Settings</h1>
          <p className="text-sm text-muted-foreground mb-8">
            Tune how Donna shows up for you.
          </p>

          {/* Account */}
          <Card className="mb-5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="h-4 w-4 text-primary" /> Account
              </CardTitle>
              <CardDescription>
                Your identity in Donna. Email comes from your sign-in provider.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Name">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="What should Donna call you?"
                  disabled={loading}
                />
              </Field>
              <Field label="Email">
                <div className="flex items-center gap-2 h-10 px-3 rounded-md border border-input bg-muted/30 text-sm text-muted-foreground">
                  <Mail className="h-3.5 w-3.5" />
                  {email}
                  {!isAuthed && (
                    <span className="ml-auto text-[10px] uppercase tracking-wider text-muted-foreground">
                      Demo
                    </span>
                  )}
                </div>
              </Field>
            </CardContent>
          </Card>

          {/* Schedule */}
          <Card className="mb-5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-primary" /> Schedule
              </CardTitle>
              <CardDescription>
                When your day starts and ends — Donna uses these to fire the briefing and wrap.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4">
              <Field label="Wake time">
                <Input
                  type="time"
                  value={wake}
                  onChange={(e) => setWake(e.target.value)}
                  disabled={loading}
                />
              </Field>
              <Field label="End-of-day">
                <Input
                  type="time"
                  value={eod}
                  onChange={(e) => setEod(e.target.value)}
                  disabled={loading}
                />
              </Field>
            </CardContent>
          </Card>

          {/* Working style */}
          <Card className="mb-5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" /> Working style
              </CardTitle>
              <CardDescription>
                A short description of how you work best. Donna folds this into every plan.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Input
                value={workingStyle}
                onChange={(e) => setWorkingStyle(e.target.value)}
                placeholder="e.g. focus best in the morning, hate context-switching"
                disabled={loading}
              />
            </CardContent>
          </Card>

          {/* Appearance */}
          <Card className="mb-5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="h-4 w-4 text-primary" /> Appearance
              </CardTitle>
              <CardDescription>Theme preference saved on this device.</CardDescription>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button
                variant={theme === "dark" ? "default" : "outline"}
                onClick={() => applyTheme("dark")}
              >
                Dark
              </Button>
              <Button
                variant={theme === "light" ? "default" : "outline"}
                onClick={() => applyTheme("light")}
              >
                Light
              </Button>
            </CardContent>
          </Card>

          {/* Notifications */}
          <Card className="mb-5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-4 w-4 text-primary" /> Notifications
              </CardTitle>
              <CardDescription>
                Use the bell button in the top bar to enable browser push for briefings and event
                reminders.
              </CardDescription>
            </CardHeader>
          </Card>

          {/* Save bar */}
          <div className="flex items-center justify-between mb-10">
            <Button variant="ghost" onClick={() => router.back()}>
              Cancel
            </Button>
            <Button onClick={save} disabled={saving || loading}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>

          {/* Danger zone */}
          <Card className="border-destructive/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-destructive">
                <LogOut className="h-4 w-4" /> Sign out
              </CardTitle>
              <CardDescription>
                You can sign back in any time. Demo data stays in the shared sandbox.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={handleSignOut}>
                Sign out
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}
