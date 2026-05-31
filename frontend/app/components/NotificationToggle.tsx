"use client";

import React, { useEffect, useState } from "react";
import { getVapidKey, subscribePush, unsubscribePush } from "../../lib/api";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

type State = "unsupported" | "off" | "on" | "busy";

export default function NotificationToggle() {
  const [state, setState] = useState<State>("off");

  useEffect(() => {
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
        alert("Push isn't configured on the server.");
        setState("off");
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
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
    } catch (e) {
      console.error("Failed to enable notifications", e);
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
    } catch (e) {
      console.error("Failed to disable notifications", e);
    }
    setState("off");
  };

  if (state === "unsupported") return null;

  const on = state === "on";
  return (
    <button
      onClick={on ? disable : enable}
      disabled={state === "busy"}
      title={on ? "Disable briefing notifications" : "Enable briefing notifications"}
      aria-label="Toggle notifications"
      className="w-8 h-8 rounded-full flex items-center justify-center text-sm transition-colors"
      style={{
        backgroundColor: on ? "var(--accent)" : "var(--surface-2)",
        color: on ? "var(--accent-contrast)" : "var(--muted)",
        border: "1px solid var(--border)",
        cursor: state === "busy" ? "wait" : "pointer",
      }}
    >
      {on ? "🔔" : "🔕"}
    </button>
  );
}
