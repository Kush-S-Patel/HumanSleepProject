"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Worklist" },
  { href: "/upload", label: "Upload" },
  { href: "/concordance", label: "Concordance" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-5 text-sm">
      {links.map((l) => {
        const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            className={
              active
                ? "font-medium text-[var(--color-teal)] border-b-2 border-[var(--color-teal)] pb-0.5"
                : "text-[var(--color-fog-400)] hover:text-[var(--color-fog-100)]"
            }
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
