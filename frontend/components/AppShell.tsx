"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { getUsername, setSession } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: "◧" },
  { href: "/new", label: "New task", icon: "✦" },
  { href: "/history", label: "History", icon: "≣" },
  { href: "/files", label: "Files", icon: "⬇" },
  { href: "/system", label: "System", icon: "⚙" },
  { href: "/login", label: "Account", icon: "◎" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
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
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="sidebar-foot">
          <span className="live">
            <span className="live-dot" /> local &amp; private
          </span>
          <a
            className="sidebar-link"
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
          >
            API docs ↗
          </a>
          <a
            className="sidebar-link"
            href="http://localhost:8081"
            target="_blank"
            rel="noreferrer"
          >
            Airflow ↗
          </a>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <div className="crumb">
              {NAV.find((item) => isActive(pathname, item.href))?.label ??
                "Mini AI"}
            </div>
            <div className="tag">Private LLM · LangGraph · MCP · FastAPI</div>
          </div>
          <div className="actions">
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
                  Logout
                </button>
              </>
            ) : null}
            <Link className="primary small" href="/new">
              + New task
            </Link>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
