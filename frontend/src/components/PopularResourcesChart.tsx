import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useMediaQuery } from "../hooks/useMediaQuery";
import type { PopularResource } from "../types/models";

const BAR_COLOR = "#2563eb"; // brand-600 — validated (lightness, chroma, contrast) for a single series
const GRID = "#e2e8f0"; // slate-200, one step off the card surface
const AXIS_TEXT = "#64748b"; // slate-500 (text token, never the series color)

const truncate = (s: string, n = 26) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

type TickProps = { x: number; y: number; payload: { value: string } };

/** Single-line category label (Recharts' default tick word-wraps); full title on hover. */
function CategoryTick({ x, y, payload, maxChars }: TickProps & { maxChars: number }) {
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fill={AXIS_TEXT} fontSize={12}>
      <title>{payload.value}</title>
      {truncate(payload.value, maxChars)}
    </text>
  );
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: PopularResource }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lift">
      <p className="max-w-[220px] font-semibold text-ink">{r.title}</p>
      <p className="mt-1 flex items-center gap-1.5 text-ink-soft">
        <span className="h-2 w-2 rounded-sm" style={{ background: BAR_COLOR }} aria-hidden />
        {r.borrow_count.toLocaleString()} borrows
      </p>
      <p className="text-ink-muted">{r.reservation_count.toLocaleString()} active reservations</p>
    </div>
  );
}

/**
 * Single-series horizontal bar chart of borrow counts. One series, so no legend —
 * the card title names it. The ranking table beside it is the accessible table view.
 */
export function PopularResourcesChart({ data }: { data: PopularResource[] }) {
  const narrow = useMediaQuery("(max-width: 640px)");
  const rows = [...data].sort((a, b) => b.borrow_count - a.borrow_count);
  const height = Math.max(160, rows.length * 40 + 24);

  return (
    <div style={{ height }} role="img" aria-label={`Bar chart of borrow counts for ${rows.length} most popular resources`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }} barCategoryGap={8}>
          <CartesianGrid horizontal={false} stroke={GRID} strokeWidth={1} />
          <XAxis type="number" allowDecimals={false} tick={{ fill: AXIS_TEXT, fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="title"
            width={narrow ? 112 : 180}
            tick={(props: TickProps) => <CategoryTick {...props} maxChars={narrow ? 15 : 26} />}
            axisLine={{ stroke: GRID }}
            tickLine={false}
          />
          <Tooltip cursor={{ fill: "rgb(37 99 235 / 0.06)" }} content={<ChartTooltip />} />
          <Bar dataKey="borrow_count" name="Borrows" fill={BAR_COLOR} barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            <LabelList dataKey="borrow_count" position="right" style={{ fill: "#0f172a", fontSize: 12, fontWeight: 600 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
