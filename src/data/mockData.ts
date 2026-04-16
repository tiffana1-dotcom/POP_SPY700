/** Barrel — domain types + catalog (snapshots → opportunity → enriched products). */
export * from "./types";
export type { EnrichedProduct } from "./catalog";
export {
  enrichedProducts,
  getEnrichedByAsin,
  getProductById,
  categoryTrends,
  dashboardKpis,
  watchlistEntries,
} from "./catalog";
