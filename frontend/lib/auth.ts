import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";

const GOOGLE_ID = process.env.GOOGLE_CLIENT_ID || "";
const GOOGLE_SECRET = process.env.GOOGLE_CLIENT_SECRET || "";
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SessionUser {
  id?: string;
  email?: string | null;
  name?: string | null;
  image?: string | null;
  provider?: string;
}

/**
 * NextAuth config.
 *
 * - Google is enabled when GOOGLE_CLIENT_ID / SECRET are present.
 * - Credentials is always available — backed by POST /auth/login on the backend.
 * - On any successful Google sign-in we POST /auth/oauth-upsert so Google and
 *   email-password users share the same `users` collection in Mongo.
 */
export const authOptions: NextAuthOptions = {
  providers: [
    ...(GOOGLE_ID && GOOGLE_SECRET
      ? [GoogleProvider({ clientId: GOOGLE_ID, clientSecret: GOOGLE_SECRET })]
      : []),
    CredentialsProvider({
      id: "credentials",
      name: "Email & password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(creds) {
        if (!creds?.email || !creds?.password) return null;
        try {
          const res = await fetch(`${BACKEND_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: creds.email,
              password: creds.password,
            }),
          });
          if (!res.ok) return null;
          const data = (await res.json()) as { user?: SessionUser };
          if (!data?.user?.id) return null;
          return {
            id: data.user.id,
            email: data.user.email ?? undefined,
            name: data.user.name ?? undefined,
            image: data.user.image ?? undefined,
          };
        } catch {
          return null;
        }
      },
    }),
  ],
  session: { strategy: "jwt" },
  pages: {
    signIn: "/?login=open",
  },
  callbacks: {
    async signIn({ user, account }) {
      // Google succeeded — upsert into Mongo so we have one user record.
      if (account?.provider === "google" && user?.email) {
        try {
          await fetch(`${BACKEND_URL}/auth/oauth-upsert`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: user.email,
              name: user.name,
              image: user.image,
            }),
          });
        } catch {
          // Don't block the sign-in if Mongo is briefly unreachable.
        }
      }
      return true;
    },
    async session({ session, token }) {
      if (session.user && token.sub) {
        (session.user as SessionUser).id = token.sub;
      }
      return session;
    },
  },
};

export function googleEnabled(): boolean {
  return Boolean(GOOGLE_ID && GOOGLE_SECRET);
}
