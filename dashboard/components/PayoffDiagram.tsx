"use client";

/**
 * Long-call payoff at expiry, drawn as inline SVG.
 *
 * A single leg, so the shape is simple: flat at minus the premium up to the
 * strike, then a 45° climb. What matters visually is where three prices sit
 * against it — breakeven, the signal's stop, and its 3R target — because those
 * are what the bot actually acts on.
 */
export default function PayoffDiagram({
  strike,
  premium,
  spot,
  stop,
  target,
  width = 320,
  height = 150,
  compact = false,
}: {
  strike: number;
  premium: number;
  spot: number | null;
  stop?: number;
  target?: number;
  width?: number;
  height?: number;
  compact?: boolean;
}) {
  const breakeven = strike + premium;
  const lo = Math.min(strike * 0.94, stop ?? Infinity, spot ?? Infinity) * 0.995;
  const hi = Math.max(strike * 1.08, target ?? 0, spot ?? 0, breakeven) * 1.005;
  const maxGain = Math.max(hi - breakeven, premium) * 1.1;

  const x = (p: number) => ((p - lo) / (hi - lo)) * width;
  const y = (v: number) => height / 2 - (v / maxGain) * (height / 2 - 8);

  const pts = [lo, strike, hi].map((p) => `${x(p)},${y(Math.max(p - strike, 0) - premium)}`);
  const zeroY = y(0);

  const marker = (p: number | undefined | null, color: string, label: string) =>
    p == null || p < lo || p > hi ? null : (
      <g key={label}>
        <line x1={x(p)} y1={4} x2={x(p)} y2={height - 4} stroke={color} strokeWidth={1}
              strokeDasharray="3 3" opacity={0.8} />
        {!compact && (
          <text x={x(p) + 3} y={12} fontSize={9} fill={color} className="font-mono2">{label}</text>
        )}
      </g>
    );

  return (
    <svg width={width} height={height} role="img" aria-label="payoff at expiry">
      <line x1={0} y1={zeroY} x2={width} y2={zeroY} stroke="var(--baseline)" strokeWidth={1} />
      <polyline points={pts.join(" ")} fill="none" stroke="var(--series-2)" strokeWidth={2} />
      {marker(breakeven, "var(--ink-muted)", "BE")}
      {marker(stop, "var(--level-stop)", "stop")}
      {marker(target, "var(--level-target)", "3R")}
      {spot != null && spot >= lo && spot <= hi && (
        <circle cx={x(spot)} cy={y(Math.max(spot - strike, 0) - premium)} r={3.5}
                fill="var(--ink-primary)" />
      )}
    </svg>
  );
}
