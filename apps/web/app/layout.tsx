import type { Metadata } from "next";
import { Source_Serif_4, Source_Sans_3, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Brand } from "./components/Brand";
import { NavLinks } from "./components/NavLinks";

const display = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
  display: "swap",
});
const body = Source_Sans_3({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-source-sans",
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "HSP Lab — Human Sleep Project",
  description:
    "Research workbench for the Human Sleep Project: cohort browsing, CAISR automated PSG scoring, and AI–human concordance evaluation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body
        style={{
          fontFamily: "var(--font-source-sans)",
          ["--font-display" as string]: "var(--font-source-serif)",
          ["--font-body" as string]: "var(--font-source-sans)",
          ["--font-mono" as string]: "var(--font-ibm-plex-mono)",
        }}
      >
        <div className="min-h-screen flex flex-col">
          <header className="border-b hairline bg-[var(--color-surface)]">
            <div className="mx-auto flex h-14 max-w-[1200px] items-center justify-between px-5">
              <Brand />
              <NavLinks />
            </div>
          </header>

          <div className="border-b hairline bg-[var(--color-muted)]/60">
            <div className="mx-auto max-w-[1200px] px-5 py-2 text-[12px] leading-relaxed text-[var(--color-fog-400)]">
              Data science project on the{" "}
              <span className="font-medium text-[var(--color-fog-300)]">Human Sleep Project (HSP)</span>{" "}
              dataset · automated scoring via{" "}
              <span className="font-medium text-[var(--color-fog-300)]">CAISR</span> · research /
              decision-support only, not a clinical diagnosis
            </div>
          </div>

          <main className="mx-auto w-full max-w-[1200px] flex-1 px-5 py-8">{children}</main>

          <footer className="border-t hairline bg-[var(--color-surface)]">
            <div className="mx-auto max-w-[1200px] px-5 py-6 text-[12px] text-[var(--color-fog-500)]">
              HSP Lab is a research prototype built on de-identified multi-center PSG data from the
              Human Sleep Project (BDSP). Automated CAISR outputs must be reviewed against the raw
              recording by a qualified clinician before any clinical use.
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
