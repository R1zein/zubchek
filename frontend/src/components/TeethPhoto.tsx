import { useState } from "react";
import { useLanguage } from "@/contexts/LanguageContext";

// A frame from the analysis: polygon [[x, y], ...] (tilted teeth get a rotated
// frame) or an older box [x0, y0, x1, y1]; coordinates are 0..1 of the photo.
export type Frame = number[][] | number[];

interface TeethPhotoProps {
  src: string;
  toothBoxes?: Record<string, Frame> | null;
  quadrantBoxes?: Record<string, Frame> | null;
}

const YELLOW = "#ffd700";
const GREEN = "#00c850";

function toPoints(frame: Frame): number[][] {
  if (typeof frame[0] === "number") {
    const [x0, y0, x1, y1] = frame as number[];
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  }
  return frame as number[][];
}

/** The report photo with the analysed teeth framed: yellow per tooth, green per quadrant. */
export default function TeethPhoto({ src, toothBoxes, quadrantBoxes }: TeethPhotoProps) {
  const { lang } = useLanguage();
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  if (!toothBoxes || Object.keys(toothBoxes).length === 0) {
    return (
      <img
        src={src}
        alt="Teeth photo"
        className="w-48 h-36 sm:w-64 sm:h-48 object-cover rounded-xl border border-gray-200 dark:border-gray-700"
      />
    );
  }

  // Draw in the photo's own pixel space so frames and labels keep their shape.
  const w = size?.w ?? 1;
  const h = size?.h ?? 1;
  const stroke = Math.max(w, h) / 250;
  const font = Math.max(w, h) / 40;
  const points = (f: Frame) => toPoints(f).map(([x, y]) => `${x * w},${y * h}`).join(" ");

  return (
    <figure className="w-full max-w-xs sm:max-w-sm">
      <div className="relative">
        <img
          src={src}
          alt="Teeth photo"
          onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
          className="block w-full h-auto rounded-xl border border-gray-200 dark:border-gray-700"
        />
        {size && (
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox={`0 0 ${w} ${h}`}
            aria-hidden="true"
          >
            {Object.entries(quadrantBoxes ?? {}).map(([q, f]) => (
              <polygon key={`q${q}`} points={points(f)} fill="none" stroke={GREEN} strokeWidth={stroke * 1.2} />
            ))}
            {Object.entries(toothBoxes).map(([id, f]) => {
              const pts = toPoints(f);
              const cx = (pts.reduce((s, p) => s + p[0], 0) / pts.length) * w;
              const cy = (pts.reduce((s, p) => s + p[1], 0) / pts.length) * h;
              return (
                <g key={id}>
                  <polygon points={points(f)} fill="none" stroke={YELLOW} strokeWidth={stroke} />
                  <text
                    x={cx}
                    y={cy}
                    fontSize={font}
                    fontWeight={700}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={YELLOW}
                    stroke="#000"
                    strokeWidth={font / 8}
                    paintOrder="stroke"
                  >
                    {id}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </div>
      <figcaption className="mt-1.5 text-xs text-center text-gray-500 dark:text-gray-400">
        {lang === "ru"
          ? "Жёлтые рамки — проанализированные зубы, зелёные — квадранты"
          : "Yellow frames — analysed teeth, green — quadrants"}
      </figcaption>
    </figure>
  );
}
