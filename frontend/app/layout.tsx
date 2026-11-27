import type { Metadata } from "next";

import AppShell from "@/components/AppShell";
import { LanguageProvider } from "@/components/LanguageProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Mini AI Task Agent",
  description:
    "Agent privé qui envoie des emails et crée des rapports PDF/HTML. Private agent that sends emails and builds PDF/HTML reports.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>
        <LanguageProvider>
          <AppShell>{children}</AppShell>
        </LanguageProvider>
      </body>
    </html>
  );
}
