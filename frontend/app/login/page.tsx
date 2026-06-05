import { redirect } from "next/navigation";

/**
 * Legacy /login route. The login UI lives in a modal on the landing page now,
 * so we redirect any direct hits (including NextAuth's default signIn page) to
 * the landing with the modal auto-opened.
 */
export default function LoginRedirect() {
  redirect("/?login=open");
}
