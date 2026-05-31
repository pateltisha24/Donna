import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Donna — Your AI Secretary",
  description: "Personal AI secretary powered by Donna",
};

// Apply the saved theme before first paint to avoid a flash.
const themeScript = `
(function() {
  try {
    var t = localStorage.getItem('donna_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body
        className="font-sans antialiased h-full"
        style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}
      >
        {children}
      </body>
    </html>
  );
}
