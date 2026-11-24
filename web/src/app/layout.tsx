import type { Metadata, Viewport } from "next";
import { Instrument_Sans } from "next/font/google";

import { ThemeProvider } from "@/components/theme";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

const sans = Instrument_Sans({ variable: "--font-sans", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: { default: "Job Radar", template: "%s · Job Radar" },
  description: "Daily matches from my target companies",
  robots: { index: false, follow: false, nocache: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f6f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1820" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full">
        <ThemeProvider>
          {children}
          <Toaster position="top-center" />
        </ThemeProvider>
      </body>
    </html>
  );
}
