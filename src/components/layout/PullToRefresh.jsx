import React, { useRef, useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";

export default function PullToRefresh({ children, onRefresh }) {
  const startY = useRef(0);
  const [pullDistance, setPullDistance] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const canPull = () => window.scrollY <= 0 && !refreshing;

  const handleTouchStart = (event) => {
    if (!canPull()) return;
    startY.current = event.touches[0].clientY;
  };

  const handleTouchMove = (event) => {
    if (!canPull() || !startY.current) return;
    const distance = Math.max(0, event.touches[0].clientY - startY.current);
    setPullDistance(Math.min(distance * 0.45, 72));
  };

  const handleTouchEnd = async () => {
    if (pullDistance < 56) {
      setPullDistance(0);
      startY.current = 0;
      return;
    }

    setRefreshing(true);
    setPullDistance(56);

    try {
      await onRefresh?.();
    } finally {
      setRefreshing(false);
      setPullDistance(0);
      startY.current = 0;
    }
  };

  return (
    <div onTouchStart={handleTouchStart} onTouchMove={handleTouchMove} onTouchEnd={handleTouchEnd}>
      <motion.div
        aria-hidden="true"
        className="pointer-events-none fixed left-1/2 top-[calc(env(safe-area-inset-top)+0.75rem)] z-30 flex -translate-x-1/2 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-500 shadow-sm lg:hidden dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"
        animate={{ opacity: pullDistance > 8 ? 1 : 0, y: pullDistance > 8 ? 0 : -12 }}
        transition={{ duration: 0.18 }}
      >
        {refreshing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {refreshing ? "Refreshing…" : "Pull to refresh"}
      </motion.div>
      <motion.div animate={{ y: pullDistance }} transition={{ duration: refreshing ? 0.18 : 0 }}>
        {children}
      </motion.div>
    </div>
  );
}