import { watchlistEntries, enrichedProducts, getEnrichedByAsin } from "@/data/mockData";
import { WatchlistRow } from "@/components/WatchlistRow";

export function WatchlistPage() {
  const rows = watchlistEntries
    .map((entry) => {
      const product = getEnrichedByAsin(entry.asin);
      if (!product) return null;
      return { entry, product };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          Buyer watchlist
        </h1>
        <p className="mt-1 text-sm text-slate-600 max-w-2xl leading-relaxed">
          Monitored ASINs with day-over-day Opportunity Score movement — built for
          ongoing import / watch / avoid decisions, not a static saved list.
        </p>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-card">
        <div className="overflow-x-auto">
          <table className="min-w-[920px] w-full text-left">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3 font-medium">Product</th>
                <th className="px-4 py-3 font-medium">Opportunity score</th>
                <th className="px-4 py-3 font-medium">Yesterday → today</th>
                <th className="px-4 py-3 font-medium">Recommendation</th>
                <th className="px-4 py-3 font-medium">Alert severity</th>
                <th className="px-4 py-3 font-medium">Status summary</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ entry, product }) => (
                <WatchlistRow key={entry.asin} entry={entry} product={product} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Tracking {enrichedProducts.length} ASINs with multi-day snapshots ·{" "}
        {watchlistEntries.length} actively monitored
      </p>
    </div>
  );
}
