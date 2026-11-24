import { cn } from "cn";

import { scoreTone } from "@/lib/format";

const TONE = {
  high: "text-score-high",
  mid: "text-score-mid",
  low: "text-score-low",
};

/** The radar dial: an arc filled to the score, with the number in the middle. */
export function ScoreDial({ score, size = 52, className }: { score: number; size?: number; className?: string }) {
  const stroke = size >= 48 ? 5 : 4;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const filled = (Math.max(0, Math.min(100, score)) / 100) * c;
  const tone = scoreTone(score);
  return (
    <div
      className={cn("relative grid shrink-0 place-items-center", TONE[tone], className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Fit score ${score} out of 100`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-score-track" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          stroke="currentColor"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c}`}
        />
      </svg>
      <span
        className="tnum absolute font-semibold tracking-tight text-foreground"
        style={{ fontSize: size >= 48 ? 17 : 13 }}
      >
        {score}
      </span>
    </div>
  );
}
