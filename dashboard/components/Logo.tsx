/**
 * The DeltaForge mark: a delta split by a forge line.
 *
 * Drawn inline rather than loaded from `public/` so it can take its colour
 * from the live theme tokens — the same reason the charts read their palette
 * at render time instead of hard-coding it.
 */
export default function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role="img"
      aria-label="DeltaForge"
      style={{ display: "block" }}
    >
      <defs>
        <linearGradient id="df-mark" x1="32" y1="10" x2="32" y2="55" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--series-2)" stopOpacity="0.85" />
          <stop offset="1" stopColor="var(--accent)" />
        </linearGradient>
      </defs>
      <path d="M32 10 L49 41 L15 41 Z" fill="url(#df-mark)" />
      <path d="M13.5 45 L50.5 45 L56 55 L8 55 Z" fill="var(--accent)" />
    </svg>
  );
}
