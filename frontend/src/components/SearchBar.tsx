import { Search, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { cx } from "./ui";

export function SearchBar({
  initialValue = "",
  onSearch,
  placeholder = "Search titles, authors or topics…",
  size = "md",
  autoFocus,
  className,
}: {
  initialValue?: string;
  onSearch(query: string): void;
  placeholder?: string;
  size?: "md" | "lg";
  autoFocus?: boolean;
  className?: string;
}) {
  const [value, setValue] = useState(initialValue);
  useEffect(() => setValue(initialValue), [initialValue]);

  function submit(e: FormEvent) {
    e.preventDefault();
    onSearch(value.trim());
  }

  return (
    <form role="search" onSubmit={submit} className={cx("relative flex w-full items-center", className)}>
      <label htmlFor="catalog-search" className="sr-only">
        Search the catalog
      </label>
      <Search className={cx("pointer-events-none absolute left-4 text-ink-muted", size === "lg" ? "h-5 w-5" : "h-4 w-4")} aria-hidden />
      <input
        id="catalog-search"
        type="search"
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        maxLength={500}
        className={cx(
          "w-full rounded-xl border border-slate-300 bg-white text-ink shadow-sm transition placeholder:text-ink-muted focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/15 [&::-webkit-search-cancel-button]:hidden",
          size === "lg" ? "h-14 pl-12 pr-32 text-base" : "h-11 pl-10 pr-28 text-sm",
        )}
      />
      {value && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => {
            setValue("");
            onSearch("");
          }}
          className={cx("absolute rounded-md p-1.5 text-ink-muted hover:bg-slate-100 hover:text-ink", size === "lg" ? "right-28" : "right-24")}
        >
          <X className="h-4 w-4" />
        </button>
      )}
      <button
        type="submit"
        className={cx(
          "absolute right-1.5 rounded-lg bg-brand-600 font-semibold text-white transition hover:bg-brand-700",
          size === "lg" ? "h-11 px-5 text-sm" : "h-8 px-4 text-sm",
        )}
      >
        Search
      </button>
    </form>
  );
}
