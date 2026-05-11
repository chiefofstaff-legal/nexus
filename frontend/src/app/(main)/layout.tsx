"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";

// -- Nav definitions ----------------------------------------------------------
// Order reflects operator workflow: capture first, search/review after,
// administration last. Groups separate the command layer from the reference
// layer so the sidebar reads top-down like the daily routine.

interface NavItem {
  href: string;
  label: string;
  caption: string;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/", label: "Dashboard", caption: "Command centre" },
  { href: "/time", label: "Time", caption: "Voice billing" },
  { href: "/tasks", label: "Tasks", caption: "Delegation" },
  { href: "/email", label: "Email", caption: "Voice drafting" },
  { href: "/calendar", label: "Calendar", caption: "Voice events" },
  { href: "/drafting", label: "Drafting", caption: "AI templates" },
  { href: "/search", label: "Search", caption: "Semantic" },
];

const SECONDARY_NAV: NavItem[] = [
  { href: "/matters", label: "Matters", caption: "Client engagements" },
  { href: "/documents", label: "Documents", caption: "Ingest + classify" },
  { href: "/graph", label: "Graph", caption: "Entities" },
  { href: "/sops", label: "SOPs", caption: "Workflows" },
  { href: "/sharepoint", label: "SharePoint", caption: "Sync" },
];

// -- Sidebar link (small primitive keeps CC low) -----------------------------

function SidebarLink({ item, active }: { item: NavItem; active: boolean }) {
  const base = "block px-5 py-3 transition-colors duration-200 border-l-2";
  const cls = active
    ? "border-l-[#b08d57] bg-[#0f1d2e] text-white"
    : "border-l-transparent text-[#9ca3af] hover:text-white hover:bg-[#0f1d2e]";
  return (
    <a href={item.href} className={`${base} ${cls}`}>
      <div className="font-mono text-xs tracking-widest uppercase">
        {item.label}
      </div>
      <div className="font-mono text-[10px] tracking-wider text-[#6b7280] mt-0.5">
        {item.caption}
      </div>
    </a>
  );
}

function NavGroup({
  title,
  items,
  pathname,
}: {
  title: string;
  items: NavItem[];
  pathname: string;
}) {
  return (
    <div>
      <div className="px-5 py-2 font-mono text-[10px] tracking-widest uppercase text-[#6b7280]">
        {title}
      </div>
      {items.map((item) => (
        <SidebarLink
          key={item.href}
          item={item}
          active={isActive(pathname, item.href)}
        />
      ))}
    </div>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

// -- Layout ------------------------------------------------------------------

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-full bg-[#f8f8f8]">
      <SidebarDrawer
        pathname={pathname}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <TopBar onMenu={() => setMobileOpen(true)} pathname={pathname} />
        <main
          className="flex-1 max-w-7xl mx-auto w-full px-6 py-10 md:py-12"
          role="main"
        >
          {children}
        </main>
        <Footer />
      </div>
    </div>
  );
}

// -- Sidebar drawer (desktop fixed + mobile overlay) --------------------------

function SidebarDrawer({
  pathname,
  mobileOpen,
  onClose,
}: {
  pathname: string;
  mobileOpen: boolean;
  onClose: () => void;
}) {
  const baseClass =
    "w-64 bg-[#0a1628] text-white flex flex-col border-r border-[#1f2937]";
  return (
    <>
      {/* Desktop */}
      <aside className={`hidden md:flex sticky top-0 h-screen overflow-y-auto ${baseClass}`} role="navigation">
        <SidebarBranding />
        <nav className="flex-1 py-4 space-y-6 overflow-y-auto">
          <NavGroup title="Capture" items={PRIMARY_NAV} pathname={pathname} />
          <NavGroup title="Library" items={SECONDARY_NAV} pathname={pathname} />
        </nav>
        <SidebarFooter />
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={onClose}
            aria-hidden="true"
          />
          <aside className={`relative ${baseClass}`} role="navigation">
            <SidebarBranding onClose={onClose} />
            <nav className="flex-1 py-4 space-y-6 overflow-y-auto">
              <NavGroup title="Capture" items={PRIMARY_NAV} pathname={pathname} />
              <NavGroup title="Library" items={SECONDARY_NAV} pathname={pathname} />
            </nav>
            <SidebarFooter />
          </aside>
        </div>
      )}
    </>
  );
}

function SidebarBranding({ onClose }: { onClose?: () => void }) {
  return (
    <div className="px-5 py-6 border-b border-[#1f2937] flex items-center justify-between">
      <div>
        <div className="text-xl font-bold tracking-tighter text-white">
          ChiefOfStaff
        </div>
        <div className="font-mono text-[10px] tracking-widest uppercase text-[#b08d57] mt-1">
          .pro
        </div>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="md:hidden text-[#9ca3af] hover:text-white font-mono text-xs tracking-widest uppercase"
          aria-label="Close menu"
        >
          Close
        </button>
      )}
    </div>
  );
}

function SidebarFooter() {
  return (
    <div className="px-5 py-4 border-t border-[#1f2937] font-mono text-[10px] tracking-widest uppercase text-[#6b7280]">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 bg-[#b08d57] inline-block animate-pulse" />
        Audit chain active
      </div>
    </div>
  );
}

function TopBar({
  onMenu,
  pathname,
}: {
  onMenu: () => void;
  pathname: string;
}) {
  const current =
    PRIMARY_NAV.concat(SECONDARY_NAV).find((i) => isActive(pathname, i.href)) ?? {
      label: "Dashboard",
      caption: "Command centre",
    };
  return (
    <header
      className="sticky top-0 z-30 border-b border-[#d1d5db] bg-white"
      role="banner"
    >
      <div className="px-6 py-4 flex items-center gap-4">
        <button
          onClick={onMenu}
          className="md:hidden border border-[#d1d5db] px-3 py-2 font-mono text-[10px] tracking-widest uppercase hover:border-[#0a1628] transition-colors duration-200"
          aria-label="Open menu"
        >
          Menu
        </button>
        <div>
          <div className="font-mono text-[10px] tracking-widest uppercase text-[#6b7280]">
            {current.caption}
          </div>
          <div className="text-lg font-bold tracking-tight text-[#0a1628]">
            {current.label}
          </div>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="border-t border-[#d1d5db] bg-white" role="contentinfo">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between font-mono text-[10px] tracking-widest uppercase text-[#6b7280]">
        <span>chiefofstaff.pro x CodeTonight</span>
      </div>
    </footer>
  );
}
