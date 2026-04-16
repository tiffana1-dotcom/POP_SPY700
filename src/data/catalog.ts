import { computeOpportunity, type OpportunityResult } from "./opportunityEngine";
import { productSeeds } from "./productSeeds";
import { snapshotsSeed } from "./snapshotsSeed";
import type {
  CategoryTrend,
  Product,
  ProductSnapshot,
  ProductBuyerNotes,
  WatchlistEntry,
} from "./types";

export interface EnrichedProduct extends Product, OpportunityResult {
  buyer: ProductBuyerNotes;
  snapshots: ProductSnapshot[];
  /** Distinct signal lists seen in the rolling window */
  activeSources: string[];
}

function formatPrice(n: number): string {
  return `$${n.toFixed(2)}`;
}

function latestSnapshot(snaps: ProductSnapshot[]): ProductSnapshot {
  return [...snaps].sort(
    (a, b) => new Date(b.capturedAt).getTime() - new Date(a.capturedAt).getTime(),
  )[0];
}

function distinctSourcesInWindow(snaps: ProductSnapshot[]): string[] {
  const last = new Date(
    Math.max(...snaps.map((s) => new Date(s.capturedAt).getTime())),
  );
  const start = new Date(last);
  start.setDate(start.getDate() - 6);
  const ms = start.getTime();
  const inWin = snaps.filter((s) => new Date(s.capturedAt).getTime() >= ms);
  return [...new Set(inWin.map((s) => s.sourceType))];
}

function buildProduct(
  seed: (typeof productSeeds)[number],
  snaps: ProductSnapshot[],
): EnrichedProduct {
  const sortedSnaps = [...snaps].sort(
    (a, b) => new Date(a.capturedAt).getTime() - new Date(b.capturedAt).getTime(),
  );
  const last = latestSnapshot(sortedSnaps);
  const opp = computeOpportunity(sortedSnaps);
  const base: Product = {
    asin: seed.asin,
    title: seed.title,
    image: seed.image,
    category: seed.category,
    latestPrice: formatPrice(last.price),
    latestRating: last.rating,
    latestReviewCount: last.reviewCount,
  };
  return {
    ...base,
    ...opp,
    buyer: seed.buyer,
    snapshots: sortedSnaps,
    activeSources: distinctSourcesInWindow(sortedSnaps),
  };
}

const byAsin = new Map<string, ProductSnapshot[]>();
for (const s of snapshotsSeed) {
  const arr = byAsin.get(s.asin) ?? [];
  arr.push(s);
  byAsin.set(s.asin, arr);
}

export const enrichedProducts: EnrichedProduct[] = productSeeds.map((seed) =>
  buildProduct(seed, byAsin.get(seed.asin) ?? []),
);

export function getEnrichedByAsin(asin: string): EnrichedProduct | undefined {
  return enrichedProducts.find((p) => p.asin === asin);
}

/** @deprecated Use getEnrichedByAsin — kept for gradual migration */
export function getProductById(id: string): EnrichedProduct | undefined {
  return getEnrichedByAsin(id);
}

function mean(nums: number[]): number {
  if (nums.length === 0) return 0;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

const CATEGORY_ORDER = [
  "Functional beverages",
  "Herbal tea",
  "Mushroom coffee",
  "Collagen snacks",
  "Vitamins / supplements",
  "OTC wellness products",
];

function heatFromMomentum(m: number): CategoryTrend["heat"] {
  if (m >= 18) return "Heating Up";
  if (m <= 2) return "Saturated";
  return "Stable";
}

export const categoryTrends: CategoryTrend[] = (() => {
  const byCat = new Map<string, EnrichedProduct[]>();
  for (const p of enrichedProducts) {
    const arr = byCat.get(p.category) ?? [];
    arr.push(p);
    byCat.set(p.category, arr);
  }
  return CATEGORY_ORDER.map((name, i) => {
    const list = byCat.get(name) ?? [];
    const avgRank = mean(list.map((x) => x.rankImprovement7d));
    const avgOpp = mean(list.map((x) => x.opportunityScore));
    const momentum7dPct = Math.round(
      Math.min(55, Math.max(-8, avgRank * 0.22 + (avgOpp - 58) * 0.45)),
    );
    const heat = heatFromMomentum(momentum7dPct);
    const summary =
      heat === "Heating Up"
        ? `Avg SKU rank velocity + opportunity are outpacing last week in ${name}.`
        : heat === "Saturated"
          ? `Leaders are entrenched; whitespace is limited without differentiation in ${name}.`
          : `Momentum is constructive but not uniform across tracked ASINs in ${name}.`;
    return {
      id: `c${i + 1}`,
      name,
      momentum7dPct,
      heat,
      summary,
    };
  });
})();

export const dashboardKpis = (() => {
  const risingWeek = enrichedProducts.filter(
    (p) => p.rankImprovement7d >= 14,
  ).length;
  const breakoutAlerts = enrichedProducts.filter(
    (p) => p.recommendation === "Import" && p.opportunityScore >= 78,
  ).length;
  const heatingCats = categoryTrends.filter((c) => c.heat === "Heating Up")
    .length;
  const worthImport = enrichedProducts.filter(
    (p) => p.recommendation === "Import",
  ).length;
  return {
    risingWeek,
    breakoutAlerts,
    heatingCats,
    worthImport,
  };
})();

export const watchlistEntries: WatchlistEntry[] = [
  {
    asin: "B0ADAP01TS",
    yesterdayOpportunity: 86,
    severity: "Elevated",
    statusSummary: "Import thesis strengthening — velocity corroborated across lists",
  },
  {
    asin: "B0COL04BT",
    yesterdayOpportunity: 84,
    severity: "Critical",
    statusSummary: "Sampling window tightening — competitor noise rising in collagen",
  },
  {
    asin: "B0HERB03SM",
    yesterdayOpportunity: 63,
    severity: "Info",
    statusSummary: "Watch mode — need one more week of stable rank slope",
  },
  {
    asin: "B0VIT05EF",
    yesterdayOpportunity: 68,
    severity: "Info",
    statusSummary: "Seasonal tailwind; confirm promo calendar before PO",
  },
  {
    asin: "B0PROB08GS",
    yesterdayOpportunity: 89,
    severity: "Elevated",
    statusSummary: "Cold-chain constraints — align logistics before authorizing buy",
  },
];

export type { ProductBuyerNotes };
