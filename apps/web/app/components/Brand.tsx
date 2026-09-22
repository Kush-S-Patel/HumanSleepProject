import Link from "next/link";

export function Brand() {
  return (
    <Link href="/" className="group flex items-baseline gap-2.5">
      <span
        className="font-display text-[1.35rem] font-semibold tracking-tight text-[var(--color-fog-100)]"
        style={{ fontFamily: "var(--font-display)" }}
      >
        HSP Lab
      </span>
      <span className="hidden text-[12px] text-[var(--color-fog-500)] sm:inline">
        Human Sleep Project
      </span>
    </Link>
  );
}
