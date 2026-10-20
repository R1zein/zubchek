import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";

interface ZoneChange {
  key: string;
  ru: string;
  en: string;
  before: number;
  after: number;
  delta: number;
}

export interface Progress {
  previous_report_id?: number;
  previous_date?: string | null;
  days_between?: number | null;
  pollution_before: number;
  pollution_after: number;
  delta: number;
  trend: "improved" | "worsened" | "stable";
  improved: ZoneChange[];
  worsened: ZoneChange[];
  mature_before?: number;
  mature_after?: number;
}

// Zone names arrive in the prepositional case for use inside sentences
// ("на верхних клыках"); the card lists them standalone, so map to nominative.
const ZONE_RU: Record<string, string> = {
  upper_central: "Верхние центральные резцы",
  upper_lateral: "Верхние боковые резцы",
  upper_canine: "Верхние клыки",
  lower_central: "Нижние центральные резцы",
  lower_lateral: "Нижние боковые резцы",
  lower_canine: "Нижние клыки",
};

const daysAgo = (n: number, lang: string) => {
  if (lang !== "ru") return n === 0 ? "today" : n === 1 ? "1 day ago" : `${n} days ago`;
  if (n === 0) return "сегодня";
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word = mod10 === 1 && mod100 !== 11 ? "день" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "дня" : "дней";
  return `${n} ${word} назад`;
};

/** "Since your last test" block: index before → after and the zones that moved.
 *  Lower plaque index is better, so a negative delta is shown in green. */
export default function ProgressCard({ progress }: { progress?: Progress | null }) {
  const { lang } = useLanguage();
  if (!progress) return null;

  const { trend, delta, pollution_before, pollution_after, improved = [], worsened = [] } = progress;
  const tone =
    trend === "improved"
      ? { box: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800", text: "text-green-700 dark:text-green-400" }
      : trend === "worsened"
      ? { box: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800", text: "text-red-700 dark:text-red-400" }
      : { box: "bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700", text: "text-gray-700 dark:text-gray-300" };
  const Icon = trend === "improved" ? TrendingDown : trend === "worsened" ? TrendingUp : Minus;
  const verdict =
    trend === "improved"
      ? lang === "ru" ? "Стало лучше" : "Improved"
      : trend === "worsened"
      ? lang === "ru" ? "Стало хуже" : "Got worse"
      : lang === "ru" ? "Без существенных изменений" : "No significant change";
  const zoneName = (z: ZoneChange) => (lang === "ru" ? ZONE_RU[z.key] || z.ru : z.en.charAt(0).toUpperCase() + z.en.slice(1));

  return (
    <div className={`mb-5 sm:mb-6 p-4 rounded-2xl border ${tone.box}`}>
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <h4 className="text-base sm:text-lg font-semibold text-gray-800 dark:text-gray-100">
          {lang === "ru" ? "Динамика с прошлого теста" : "Since your last test"}
        </h4>
        {progress.days_between != null && (
          <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
            {daysAgo(progress.days_between, lang)}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Icon className={`h-6 w-6 shrink-0 ${tone.text}`} />
        <p className="text-sm text-gray-700 dark:text-gray-300">
          {lang === "ru" ? "Индекс налёта" : "Plaque index"}:{" "}
          <span className="font-semibold">{pollution_before}%</span>
          {" → "}
          <span className={`font-bold ${tone.text}`}>{pollution_after}%</span>
          <span className={`ml-1.5 text-xs font-medium ${tone.text}`}>
            ({delta > 0 ? "+" : ""}{delta})
          </span>
          <span className={`block text-xs font-medium mt-0.5 ${tone.text}`}>{verdict}</span>
        </p>
      </div>

      {(improved.length > 0 || worsened.length > 0) && (
        <div className="mt-3 space-y-1.5">
          {improved.map((z) => (
            <div key={`i-${z.key}`} className="flex justify-between gap-2 text-xs sm:text-sm">
              <span className="text-gray-700 dark:text-gray-300">✓ {zoneName(z)}</span>
              <span className="text-green-700 dark:text-green-400 font-medium whitespace-nowrap">
                {z.before}% → {z.after}%
              </span>
            </div>
          ))}
          {worsened.map((z) => (
            <div key={`w-${z.key}`} className="flex justify-between gap-2 text-xs sm:text-sm">
              <span className="text-gray-700 dark:text-gray-300">! {zoneName(z)}</span>
              <span className="text-red-700 dark:text-red-400 font-medium whitespace-nowrap">
                {z.before}% → {z.after}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
