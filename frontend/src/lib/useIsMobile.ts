"use client";

import { useEffect, useState } from "react";

/** True below the mobile breakpoint (matches Tailwind's `md`). Reactive to
 * resize/rotation, safe for SSR (starts false, corrects on mount). */
export function useIsMobile(breakpoint = 767): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const update = () => setIsMobile(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, [breakpoint]);

  return isMobile;
}
