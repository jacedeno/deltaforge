/**
 * The DeltaForge mark.
 *
 * A delta faceted down its axis — the left face catching light, the right one
 * falling into shadow — with a thin strike line near the base. The facet is
 * what carries the identity at small sizes: the line disappears below about
 * 24px, and what is left still reads as a struck wedge rather than a flat
 * triangle.
 *
 * Drawn inline rather than loaded from `public/` so it takes its colours from
 * the live theme tokens, and so the strike line can be `--page` — the gap has
 * to be whatever the surface behind it is, or it turns into a dark bar on the
 * light theme.
 */
export default function Logo({ size = 40 }: { size?: number }) {
  const id = "df";
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="DeltaForge"
         style={{ display: "block" }}>
      <defs>
        <linearGradient id={`${id}-lit`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--series-2)" stopOpacity="0.72" />
          <stop offset="1" stopColor="var(--series-2)" />
        </linearGradient>
        <linearGradient id={`${id}-shade`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--accent)" />
          <stop offset="1" stopColor="var(--accent)" stopOpacity="0.75" />
        </linearGradient>
        <clipPath id={`${id}-tri`}>
          <path d="M32 9 L55 52 L9 52 Z" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id}-tri)`}>
        <rect x="0" y="0" width="32" height="64" fill={`url(#${id}-lit)`} />
        <rect x="32" y="0" width="32" height="64" fill={`url(#${id}-shade)`} />
        <rect x="0" y="44.5" width="64" height="2.6" fill="var(--page)" />
      </g>
    </svg>
  );
}
