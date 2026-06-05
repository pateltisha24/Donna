"use client";

import * as React from "react";
import { Bell, BellOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getVapidKey, subscribePush, unsubscribePush } from "@/lib/api";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

type State = "unsupported" | "off" | "on" | "busy";

export function PushToggle() {
  const [state, setState] = React.useState<State>("off");

  React.useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => setState(sub ? "on" : "off"))
      .catch(() => setState("off"));
  }, []);

  const enable = async () => {
    setState("busy");
    try {
      const { key, enabled } = await getVapidKey();
      if (!enabled || !key) {
        toast.error("Push isn't configured on the server.");
        setState("off");
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        toast.message("Notifications denied.");
        setState("off");
        return;
      }
      const reg = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key) as unknown as BufferSource,
      });
      await subscribePush(sub.toJSON() as PushSubscriptionJSON);
      setState("on");
      toast.success("Briefing notifications enabled.");
    } catch (e) {
      console.error("Failed to enable notifications", e);
      toast.error("Couldn't enable notifications.");
      setState("off");
    }
  };

  const disable = async () => {
    setState("busy");
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await unsubscribePush(sub.endpoint);
        await sub.unsubscribe();
      }
      toast.message("Notifications disabled.");
    } catch (e) {
      console.error("Failed to disable notifications", e);
    }
    setState("off");
  };

  if (state === "unsupported") return null;
  const on = state === "on";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={on ? "default" : "ghost"}
          size="icon-sm"
          onClick={on ? disable : enable}
          disabled={state === "busy"}
          aria-label="Toggle notifications"
        >
          {on ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {on ? "Briefing notifications on" : "Enable briefing notifications"}
      </TooltipContent>
    </Tooltip>
  );
}
