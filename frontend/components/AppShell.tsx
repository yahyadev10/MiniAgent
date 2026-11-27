"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useI18n } from "@/components/LanguageProvider";
import { getUsername, setSession } from "@/lib/api";
import type { TranslationKey } from "@/lib/i18n";

const NAV: { href: string; label: TranslationKey; icon: string }[] = [
  { href: "/", label: "nav.dashboard", icon: "◧" },
  { href: "/new", label: "nav.newTask", icon: "✦" },
  { href: "/history", label: "nav.history", icon: "≣" },
  { href: "/files", label: "nav.files", icon: "⬇" },
  { href: "/system", label: "nav.system", icon: "⚙" },
  { href: "/login", label: "nav.account", icon: "◎" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { locale, toggleLocale, t } = useI18n();
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    setUsername(getUsername());
  }, [pathname]);

  return (
    <div className="app">
      <aside className="sidebar">
        <Link href="/" className="sidebar-brand">
          <span className="logo">M</span>
          <span>
            <strong>Mini AI</strong>
            <small>Task Agent</small>
          </span>
        </Link>

        <nav className="nav">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-link ${isActive(pathname, item.href) ? "active" : ""}`}
            >
              <span className="nav-icon">{item.icon}</span>
              {t(item.label)}
            </Link>
          ))}
        </nav>

        <div className="sidebar-foot">
          <span className="live">
            <span className="live-dot" /> {t("sidebar.localPrivate")}
          </span>
          <a
            className="sidebar-link"
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
          >
            {t("sidebar.apiDocs")} ↗
          </a>
          <a
            className="sidebar-link"
            href="http://localhost:8081"
            target="_blank"
            rel="noreferrer"
          >
            {t("sidebar.airflow")} ↗
          </a>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <div className="crumb">
              {NAV.find((item) => isActive(pathname, item.href))
                ? t(NAV.find((item) => isActive(pathname, item.href))!.label)
                : t("app.name")}
            </div>
            <div className="tag">{t("tagline")}</div>
          </div>
          <div className="actions">
            <button
              className="chip"
              type="button"
              onClick={toggleLocale}
              aria-label={t("lang.switch")}
            >
              {locale === "fr" ? "EN" : "FR"}
            </button>
            {username ? (
              <>
                <span className="meta">{username}</span>
                <button
                  className="chip"
                  type="button"
                  onClick={() => {
                    setSession(null, null);
                    setUsername(null);
                  }}
                >
                  {t("common.logout")}
                </button>
              </>
            ) : null}
            <Link className="primary small" href="/new">
              {t("common.newTask")}
            </Link>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
