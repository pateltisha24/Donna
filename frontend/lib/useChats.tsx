"use client";

import * as React from "react";
import {
  createChat as apiCreateChat,
  deleteChat as apiDeleteChat,
  listChats,
  renameChat as apiRenameChat,
  titleChatFromMessage,
  type Chat,
} from "@/lib/api";

const ACTIVE_KEY = "donna_active_chat";

interface ChatsState {
  chats: Chat[];
  activeId: string | null;
  loading: boolean;
}

interface ChatsApi extends ChatsState {
  setActiveId: (id: string) => void;
  refresh: () => Promise<void>;
  newChat: () => Promise<Chat>;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  /** Generate an AI title for a chat based on the first user message. */
  titleFromFirstMessage: (id: string, firstMessage: string) => Promise<string>;
}

const ChatsContext = React.createContext<ChatsApi | null>(null);

export function ChatsProvider({ children }: { children: React.ReactNode }) {
  const [chats, setChats] = React.useState<Chat[]>([]);
  const [activeId, setActiveIdState] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const setActiveId = React.useCallback((id: string) => {
    setActiveIdState(id);
    try {
      localStorage.setItem(ACTIVE_KEY, id);
    } catch {}
  }, []);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const list = await listChats();
      setChats(list);
      // Resolve active chat: saved → first → none.
      let saved: string | null = null;
      try {
        saved = localStorage.getItem(ACTIVE_KEY);
      } catch {}
      const stillValid = saved && list.some((c) => c.id === saved);
      if (stillValid && saved) {
        setActiveIdState(saved);
      } else if (list.length > 0) {
        setActiveIdState(list[0].id);
      } else {
        setActiveIdState(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const newChat = React.useCallback(async (): Promise<Chat> => {
    const chat = await apiCreateChat();
    setChats((prev) => [chat, ...prev]);
    setActiveId(chat.id);
    return chat;
  }, [setActiveId]);

  const rename = React.useCallback(async (id: string, title: string) => {
    setChats((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title } : c))
    );
    await apiRenameChat(id, title);
  }, []);

  const remove = React.useCallback(
    async (id: string) => {
      // Optimistic update.
      let nextActive = activeId;
      setChats((prev) => {
        const filtered = prev.filter((c) => c.id !== id);
        if (id === activeId) {
          nextActive = filtered[0]?.id ?? null;
        }
        return filtered;
      });
      if (nextActive !== activeId) {
        if (nextActive) setActiveId(nextActive);
        else setActiveIdState(null);
      }
      await apiDeleteChat(id);
    },
    [activeId, setActiveId]
  );

  const titleFromFirstMessage = React.useCallback(
    async (id: string, firstMessage: string) => {
      const title = await titleChatFromMessage(id, firstMessage);
      if (title) {
        setChats((prev) =>
          prev.map((c) => (c.id === id ? { ...c, title } : c))
        );
      }
      return title;
    },
    []
  );

  const value: ChatsApi = {
    chats,
    activeId,
    loading,
    setActiveId,
    refresh,
    newChat,
    rename,
    remove,
    titleFromFirstMessage,
  };

  return <ChatsContext.Provider value={value}>{children}</ChatsContext.Provider>;
}

export function useChats(): ChatsApi {
  const ctx = React.useContext(ChatsContext);
  if (!ctx) {
    throw new Error("useChats must be used inside a ChatsProvider");
  }
  return ctx;
}
