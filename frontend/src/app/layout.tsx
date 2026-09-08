import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";

import "./globals.css";
import { Providers } from "@/components/providers/Providers";

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
    { media: "(prefers-color-scheme: light)", color: "#f7f6f3" },
    { media: "(prefers-color-scheme: dark)", color: "#121110" },
  ],
};

const NO_FLASH = `(function(){try{var t=localStorage.getItem('studybuddy-theme')||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');var r=document.documentElement;r.setAttribute('data-theme',t);r.classList.toggle('dark',t==='dark');r.style.colorScheme=t;}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
