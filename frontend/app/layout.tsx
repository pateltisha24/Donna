import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Donna — Your AI Secretary",
  description: "Personal AI secretary powered by Donna",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        className="bg-donna-bg text-donna-text font-sans antialiased h-full"
        style={{ backgroundColor: "#0f0f11", color: "#e8e8f0" }}
      >
        {children}
      </body>
    </html>
  );
}
