import type { Metadata, Viewport } from "next";
import { Public_Sans, Space_Grotesk } from "next/font/google";
import { GeistMono } from "geist/font/mono";

import "katex/dist/katex.min.css";
import "./globals.css";
import { Providers } from "@/components/providers/Providers";

// All-sans, tool-shaped typography — deliberately not another editorial
// serif pairing. Space Grotesk carries the geometric, slightly technical
// "smart tutor" character in headings; Public Sans stays out of the way for
// body text and UI chrome.
const sans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});
const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: "StudyBuddy",
  description:
    "An adaptive AI study tutor — grounded explanations from your own notes, tiered practice questions with grading, study guides, and progress tracking.",
  applicationName: "StudyBuddy",
  icons: { icon: "/favicon.svg" },
  openGraph: {
    title: "StudyBuddy",
    description:
      "Upload your notes, slides or a photo of a problem. Get explanations pitched to your level, practice questions that mark themselves, study guides, and a progress dashboard.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8f9fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0f14" },
  ],
};

const NO_FLASH = `(function(){try{var t=localStorage.getItem('studybuddy-theme')||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');var r=document.documentElement;r.setAttribute('data-theme',t);r.classList.toggle('dark',t==='dark');r.style.colorScheme=t;}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sans.variable} ${display.variable} ${GeistMono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
