"use client";

import { IconContext } from "@phosphor-icons/react";

import { ThemeProvider } from "./ThemeProvider";
import { ToastViewport } from "@/components/ui/ToastViewport";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <IconContext.Provider value={{ weight: "regular", size: 16, className: "shrink-0" }}>
        {children}
        <ToastViewport />
      </IconContext.Provider>
    </ThemeProvider>
  );
}
