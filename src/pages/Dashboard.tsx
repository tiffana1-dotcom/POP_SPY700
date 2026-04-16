import { useMemo, useState } from "react";
import {
  categoryTrends,
  dashboardKpis,
  enrichedProducts,
  type EnrichedProduct,
} from "@/data/mockData";
import { KPIStatCard } from "@/components/KPIStatCard";
import { ProductCard } from "@/components/ProductCard";
import { TopOpportunitiesWeek } from "@/components/TopOpportunitiesWeek";
import { TrendCard } from "@/components/TrendCard";

const categories = [
  "All categories",
  "Functional beverages",
  "Herbal tea",
  "Mushroom coffee",
  "Collagen snacks",
  "Vitamins / supplements",
  "OTC wellness products",
] as const;

const markets = ["All markets", "Amazon US", "Amazon CA", "Amazon UK", "Amazon MX"] as const;

const timeRanges = ["Last 24 hours", "Last 7 days", "Last 30 days"] as const;

function filterProducts(
  list: EnrichedProduct[],
  query: string,
  category: (typeof categories)[number],
  market: (typeof markets)[number],
): EnrichedProduct[] {
  const q = query.trim().toLowerCase();
  return list.filter((p) => {
    const catOk =
      category === "All categories" ? true : p.category === category;
    const marketOk =
      market === "All markets" ? true : p.buyer.marketplaces.includes(market);
    const text = `${p.title} ${p.category}`.toLowerCase();
    const searchOk = q.length === 0 ? true : text.includes(q);
    return catOk && marketOk && searchOk;
  });
}

export function Dashboard() {
  const [query, setQuery] = useState("");
  const [category, setCategory] =
    useState<(typeof categories)[number]>("All categories");
  const [market, setMarket] = useState<(typeof markets)[number]>("All markets");
  const [timeRange, setTimeRange] =
    useState<(typeof timeRanges)[number]>("Last 7 days");

  const filtered = useMemo(
    () => filterProducts(enrichedProducts, query, category, market),
    [query, category, market],
  );

  const risingSorted = useMemo(() => {
    return [...filtered].sort(
      (a, b) => b.rankImprovement7d - a.rankImprovement7d,
    );
  }, [filtered]);

  const topPool = useMemo(
    () => filterProducts(enrichedProducts, query, category, market),
    [query, category, market],
  );

  return (
    <div className="space-y-8 sm:space-y-10">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-lg font-medium tracking-tight text-slate-500 sm:text-[1.05rem]">
            Live Product Radar
          </h1>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-slate-400">
            Context for the shortlist below — filters and detail grids are
            secondary.
          </p>
        </div>
        <p className="text-[11px] tabular-nums text-slate-400">
          Window: {timeRange} · Rolling 7d signals
        </p>
      </header>

      <TopOpportunitiesWeek products={topPool} />

      <div className="space-y-8 border-t border-slate-200/70 pt-8 sm:space-y-9 sm:pt-10">
        <div className="space-y-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            Refine &amp; explore
          </p>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <div className="flex-1">
              <label htmlFor="search" className="sr-only">
                Search products
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
                  <SearchIcon />
                </span>
                <input
                  id="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by title or category…"
                  className="w-full rounded-lg border border-slate-200/90 bg-white/90 py-2.5 pl-10 pr-3 text-sm text-slate-700 shadow-none placeholder:text-slate-400 focus:border-slate-300/80 focus:outline-none focus:ring-1 focus:ring-slate-200"
                />
              </div>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <FilterSelect
              label="Category"
              value={category}
              onChange={(v) => setCategory(v as (typeof categories)[number])}
              options={[...categories]}
              quiet
            />
            <FilterSelect
              label="Market"
              value={market}
              onChange={(v) => setMarket(v as (typeof markets)[number])}
              options={[...markets]}
              quiet
            />
            <FilterSelect
              label="Time range"
              value={timeRange}
              onChange={(v) => setTimeRange(v as (typeof timeRanges)[number])}
              options={[...timeRanges]}
              quiet
            />
            </div>
          </div>
        </div>

        <section>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <KPIStatCard
              label="Rising products this week"
              value={dashboardKpis.risingWeek}
              hint="ASINs with ≥14 positions of net rank lift vs week start (best rank / day)."
              muted
            />
            <KPIStatCard
              label="New breakout alerts"
              value={dashboardKpis.breakoutAlerts}
              hint="Import-grade Opportunity Score with corroborating multi-day signals."
              muted
            />
            <KPIStatCard
              label="Categories heating up"
              value={dashboardKpis.heatingCats}
              hint="Categories where average momentum index is in “Heating Up”."
              muted
            />
            <KPIStatCard
              label="Products worth importing"
              value={dashboardKpis.worthImport}
              hint="Recommendation = Import based on sustained signals, not a static scorecard."
              muted
            />
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
              Trending categories
            </h2>
            <span className="text-[10px] text-slate-400">
              Multi-day momentum index
            </span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {categoryTrends.map((t) => (
              <TrendCard key={t.id} trend={t} muted />
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                Fastest rising products
              </h2>
              <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
                Ranked by 7-day net rank improvement across snapshots.{" "}
                {filtered.length === enrichedProducts.length
                  ? "Showing all tracked ASINs."
                  : `Showing ${filtered.length} of ${enrichedProducts.length} after filters.`}
              </p>
            </div>
          </div>
          {risingSorted.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200/90 bg-white/60 p-10 text-center text-xs text-slate-500">
              No products match your search. Try clearing filters or broadening the
              category.
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {risingSorted.map((p) => (
                <ProductCard key={p.asin} product={p} muted />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  quiet,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  quiet?: boolean;
}) {
  const id = `filter-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div className="flex min-w-[160px] flex-col gap-1">
      <label
        htmlFor={id}
        className={
          quiet
            ? "text-[11px] font-medium text-slate-400"
            : "text-xs font-medium text-slate-500"
        }
      >
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={
          quiet
            ? "rounded-lg border border-slate-200/80 bg-white/90 px-3 py-2 text-sm text-slate-600 shadow-none focus:border-slate-300/80 focus:outline-none focus:ring-1 focus:ring-slate-200"
            : "rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
        }
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}
