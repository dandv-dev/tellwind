import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
type BtnSize = "sm" | "md" | "lg";

const VARIANTS: Record<BtnVariant, string> = {
  primary: "bg-accent text-accent-ink hover:brightness-110 active:scale-[0.98] shadow-[inset_0_1px_0_rgb(255_255_255/0.14)]",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-surface-2 active:scale-[0.98]",
  ghost: "text-muted hover:text-ink hover:bg-surface-2",
  danger: "text-fading hover:bg-fading-soft",
};
const SIZES: Record<BtnSize, string> = {
  sm: "h-8 px-3 text-[13px] rounded-lg gap-1.5",
  md: "h-10 px-4 text-[14px] rounded-[10px] gap-2",
  lg: "h-12 px-5 text-[15px] rounded-[10px] gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: BtnSize; loading?: boolean }>(
  function Button({ variant = "primary", size = "md", loading, className = "", children, disabled, ...rest }, ref) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={`inline-flex items-center justify-center font-medium whitespace-nowrap transition-[filter,background-color,border-color,color,transform] duration-150 ease-out disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
        {...rest}
      >
        {loading && <Spinner className="w-4 h-4" />}
        {children}
      </button>
    );
  },
);

export function ButtonLink({ href, variant = "primary", size = "md", className = "", children, ...rest }: { href: string; variant?: BtnVariant; size?: BtnSize; className?: string; children: ReactNode } & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a href={href} className={`inline-flex items-center justify-center font-medium whitespace-nowrap transition-[filter,background-color,border-color,color,transform] duration-150 ease-out ${VARIANTS[variant]} ${SIZES[size]} ${className}`} {...rest}>
      {children}
    </a>
  );
}

export function Spinner({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

const fieldCls =
  "w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-[14px] text-ink placeholder:text-faint outline-none focus:border-accent focus:ring-4 focus:ring-accent/15 transition-[border-color,box-shadow] duration-150 ease-out";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className = "", ...rest }, ref) {
  return <input ref={ref} className={`${fieldCls} h-11 ${className}`} {...rest} />;
});

export function Textarea({ className = "", ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${fieldCls} py-2.5 min-h-[72px] ${className}`} {...rest} />;
}

export function Select({ className = "", children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`${fieldCls} h-10 pr-8 appearance-none bg-no-repeat bg-[right_0.75rem_center] bg-[length:10px] ${className}`} style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%238A93A0' stroke-width='1.5' fill='none'/%3E%3C/svg%3E\")" }} {...rest}>
      {children}
    </select>
  );
}

export function Field({ label, hint, children, error }: { label: string; hint?: string; error?: string | null; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[13px] font-medium text-ink">{label}</span>
      {children}
      {error ? <span className="text-[12px] text-fading">{error}</span> : hint ? <span className="text-[12px] text-faint">{hint}</span> : null}
    </label>
  );
}

export function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative w-11 h-6 rounded-full transition-colors disabled:opacity-50 ${checked ? "bg-accent" : "bg-line-strong"}`}
    >
      <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-5" : ""}`} />
    </button>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-2xl bg-surface border border-line shadow-card ${className}`}>{children}</div>;
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-line-strong px-6 py-12 text-center flex flex-col items-center gap-3">
      {icon}
      <h3 className="font-medium text-ink">{title}</h3>
      {children && <div className="text-[14px] text-muted max-w-md">{children}</div>}
    </div>
  );
}

export function RoleBadge({ role, label }: { role: string; label: string }) {
  const cls = role === "owner" ? "text-ink" : "text-muted";
  return <span className={`inline-flex items-center rounded-md bg-surface-2 px-2 py-0.5 text-[12px] font-medium ${cls}`}>{label}</span>;
}
