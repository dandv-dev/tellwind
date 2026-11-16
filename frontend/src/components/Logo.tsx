import { AnimatePresence, motion } from "motion/react";
import { useTheme } from "../lib/theme";

type Variant = "horizontal" | "stacked" | "icon";

const SIZES: Record<Variant, { w: number; h: number }> = {
  horizontal: { w: 237.28, h: 64 },
  stacked: { w: 138.29, h: 114 },
  icon: { w: 64, h: 64 },
};

/**
 * The brand logo for the current background. When the theme flips, the old
 * version rotates out and the version for the new background turns in.
 */
export function Logo({ variant = "horizontal", height = 28, className = "", on }: { variant?: Variant; height?: number; className?: string; on?: "dark" | "light" }) {
  const { theme: pageTheme } = useTheme();
  const theme = on ?? pageTheme;
  const name = variant === "icon" ? "icon" : variant;
  const src = `/brand/logo/svg/tellwind-${name}-on-${theme === "dark" ? "dark" : "light"}.svg`;
  const { w, h } = SIZES[variant];
  const width = (w / h) * height;
  return (
    <span className={`relative inline-block align-middle ${className}`} style={{ width, height, perspective: 400 }} aria-label="Tellwind" role="img">
      <AnimatePresence initial={false}>
        <motion.img
          key={src}
          src={src}
          alt=""
          draggable={false}
          className="absolute inset-0 w-full h-full select-none"
          initial={{ opacity: 0, rotateX: -80, y: 4, filter: "blur(2px)" }}
          animate={{ opacity: 1, rotateX: 0, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, rotateX: 80, y: -4, filter: "blur(2px)" }}
          transition={{ duration: 0.45, ease: [0.3, 0.7, 0.2, 1] }}
          style={{ transformOrigin: "50% 50%" }}
        />
      </AnimatePresence>
    </span>
  );
}
