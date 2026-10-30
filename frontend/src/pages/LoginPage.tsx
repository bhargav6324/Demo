import { AlertCircle, ArrowRight, BookOpenCheck, Eye, EyeOff, Library, MessageSquareQuote, ShieldCheck, type LucideIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate, type Location } from "react-router-dom";
import { toApiError } from "../api";
import { useAuth } from "../app/AuthProvider";
import { DEMO_ACCOUNTS, type DemoAccount } from "../app/demoAccounts";
import { ROLE_LABELS } from "../app/nav";
import { useToast } from "../app/ToastProvider";
import { Button, cx } from "../components/ui";
import { config } from "../config";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const FEATURES: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: BookOpenCheck, title: "Live availability", text: "See copies, branches and shelves before you walk over." },
  { icon: MessageSquareQuote, title: "Cited AI answers", text: "Every recommendation links back to a catalog record." },
  { icon: ShieldCheck, title: "Private by design", text: "You only ever see your own loans and reservations." },
];

export function LoginPage() {
  const { user, login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: Location } | null)?.from;
  const destination = from && from.pathname !== "/login" ? `${from.pathname}${from.search}` : "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null); // "form" or a demo email

  if (user) return <Navigate to={destination} replace />;

  async function authenticate(emailValue: string, passwordValue: string, source: string) {
    if (pending) return; // ignore double submits
    setPending(source);
    setError(null);
    try {
      const signedIn = await login(emailValue.trim(), passwordValue);
      toast("success", `Welcome, ${signedIn.name}.`);
      navigate(destination, { replace: true });
    } catch (err) {
      const apiErr = toApiError(err);
      setError(apiErr.isUnauthorized ? "Incorrect email or password." : apiErr.message);
      setPassword("");
    } finally {
      setPending(null);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const errors: typeof fieldErrors = {};
    if (!email.trim()) errors.email = "Enter your university email.";
    else if (!EMAIL_RE.test(email.trim())) errors.email = "Enter a valid email address.";
    if (!password) errors.password = "Enter your password.";
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    void authenticate(email, password, "form");
  }

  const demo = (account: DemoAccount) => {
    setEmail(account.email);
    setFieldErrors({});
    void authenticate(account.email, account.password, account.email);
  };

  return (
    <div className="grid min-h-full grid-cols-1 lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <section className="relative hidden overflow-hidden bg-gradient-to-br from-brand-800 via-brand-700 to-accent-700 p-12 text-white lg:flex lg:flex-col">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.08]"
          style={{
            backgroundImage: "linear-gradient(white 1px, transparent 1px), linear-gradient(90deg, white 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
          aria-hidden
        />
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-accent-400/30 blur-3xl" aria-hidden />
        <div className="relative flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 ring-1 ring-white/25 backdrop-blur">
            <Library className="h-5 w-5" aria-hidden />
          </span>
          <span className="text-lg font-bold tracking-tight">Smart Library</span>
        </div>

        <div className="relative my-auto max-w-lg animate-fade-up py-12">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-accent-200">University Library Portal</p>
          <h2 className="text-4xl font-bold leading-tight tracking-tight">Find the right resource, faster — with an assistant that cites its sources.</h2>
          <ul className="mt-10 space-y-5">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-white/10 ring-1 ring-white/15">
                  <Icon className="h-5 w-5 text-accent-200" aria-hidden />
                </span>
                <div>
                  <p className="font-semibold">{title}</p>
                  <p className="text-sm text-brand-100/80">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-sm text-brand-100/70">For students, researchers, faculty and library staff.</p>
      </section>

      {/* Sign-in panel */}
      <section className="flex items-center justify-center bg-slate-50 px-4 py-10 sm:px-8">
        <div className="w-full max-w-md animate-fade-up">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-accent-500 text-white">
              <Library className="h-5 w-5" aria-hidden />
            </span>
            <span className="text-lg font-bold tracking-tight text-ink">Smart Library</span>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-lift sm:p-8">
            <h1 className="text-2xl font-bold tracking-tight text-ink">Sign in</h1>
            <p className="mt-1.5 text-sm text-ink-soft">Use your university account to access the library.</p>

            {error && (
              <div role="alert" className="mt-5 flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800">
                <AlertCircle className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
                {error}
              </div>
            )}

            <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
              <div>
                <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={!!fieldErrors.email}
                  aria-describedby={fieldErrors.email ? "email-error" : undefined}
                  placeholder="name@university.edu"
                  className={cx(
                    "h-11 w-full rounded-lg border bg-white px-3.5 text-sm text-ink shadow-sm transition placeholder:text-ink-muted focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/15",
                    fieldErrors.email ? "border-red-400" : "border-slate-300",
                  )}
                />
                {fieldErrors.email && (
                  <p id="email-error" className="mt-1.5 text-xs text-red-600">
                    {fieldErrors.email}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    aria-invalid={!!fieldErrors.password}
                    aria-describedby={fieldErrors.password ? "password-error" : undefined}
                    className={cx(
                      "h-11 w-full rounded-lg border bg-white pl-3.5 pr-11 text-sm text-ink shadow-sm transition focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/15",
                      fieldErrors.password ? "border-red-400" : "border-slate-300",
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-1.5 top-1.5 rounded-md p-2 text-ink-muted hover:bg-slate-100 hover:text-ink"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {fieldErrors.password && (
                  <p id="password-error" className="mt-1.5 text-xs text-red-600">
                    {fieldErrors.password}
                  </p>
                )}
              </div>

              <Button type="submit" size="lg" className="w-full" loading={pending === "form"} disabled={!!pending}>
                {pending === "form" ? "Signing in…" : "Sign in"}
                {pending !== "form" && <ArrowRight className="h-4 w-4" aria-hidden />}
              </Button>
            </form>

            {config.showDemoLogins && (
              <div className="mt-7">
                <div className="flex items-center gap-3 text-xs font-medium uppercase tracking-wider text-ink-muted">
                  <span className="h-px flex-1 bg-slate-200" />
                  Demo accounts
                  <span className="h-px flex-1 bg-slate-200" />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {DEMO_ACCOUNTS.map((account) => (
                    <button
                      key={account.email}
                      type="button"
                      onClick={() => demo(account)}
                      disabled={!!pending}
                      aria-label={`Sign in as demo ${ROLE_LABELS[account.role]}`}
                      className="group flex flex-col items-start rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-brand-300 hover:bg-brand-50/50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <span className="flex w-full items-center justify-between text-sm font-semibold text-ink">
                        {ROLE_LABELS[account.role]}
                        {pending === account.email ? (
                          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand-600 border-r-transparent" aria-hidden />
                        ) : (
                          <ArrowRight className="h-3.5 w-3.5 text-ink-muted transition group-hover:translate-x-0.5 group-hover:text-brand-600" aria-hidden />
                        )}
                      </span>
                      <span className="mt-0.5 text-xs leading-snug text-ink-muted">{account.description}</span>
                    </button>
                  ))}
                </div>
                <p className="mt-3 text-center text-xs text-ink-muted">
                  All demo accounts use password <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-ink-soft">demo123</code>
                </p>
              </div>
            )}
          </div>

          <p className="mt-6 text-center text-xs text-ink-muted">
            Prototype authentication for the hackathon demo. Sessions end when you refresh the page.
          </p>
        </div>
      </section>
    </div>
  );
}
