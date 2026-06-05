import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Providers } from "@/components/Providers";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Donna — Your AI Chief of Staff",
  description:
    "A multi-agent AI personal secretary. Plans your day, runs your calendar, remembers you, and replans when things change.",
  openGraph: {
    title: "Donna — Your AI Chief of Staff",
    description: "A multi-agent AI personal secretary that runs your day.",
    type: "website",
  },
};

// Apply saved theme before first paint to avoid a FOUC.
const themeScript = `
(function() {
  try {
    var t = localStorage.getItem('donna_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="font-sans antialiased h-full bg-background text-foreground">
        <Providers>
          <TooltipProvider delayDuration={150}>
            {children}
            <Toaster
              position="top-right"
              theme="system"
              toastOptions={{
                classNames: {
                  toast:
                    "bg-card border border-border text-card-foreground shadow-lg",
                  description: "text-muted-foreground",
                },
              }}
            />
          </TooltipProvider>
        </Providers>
      </body>
    </html>
  );
}
