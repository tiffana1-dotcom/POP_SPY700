import type { EnrichedProduct } from "@/data/mockData";

const recClass: Record<EnrichedProduct["recommendation"], string> = {
  Import:
    "bg-emerald-50 text-emerald-900 ring-1 ring-inset ring-emerald-600/15",
  Watch: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-600/15",
  Avoid: "bg-rose-50 text-rose-900 ring-1 ring-inset ring-rose-600/15",
};

interface RecommendationPanelProps {
  product: EnrichedProduct;
}

export function RecommendationPanel({ product }: RecommendationPanelProps) {
  return (
    <section className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-card">
      <h2 className="text-sm font-semibold text-slate-900">
        Recommendation
      </h2>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex rounded-md px-2.5 py-1 text-sm font-semibold ${recClass[product.recommendation]}`}
        >
          {product.recommendation}
        </span>
        <span className="text-sm text-slate-600">
          Confidence{" "}
          <span className="font-semibold text-slate-900">
            {product.confidenceLevel}
          </span>
        </span>
      </div>
      <p className="mt-4 text-sm text-slate-600 leading-relaxed">
        <span className="font-medium text-slate-800">Suggested next step: </span>
        {product.buyer.suggestedNextAction}
      </p>
    </section>
  );
}
