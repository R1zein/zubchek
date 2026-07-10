import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { createClient } from "../lib/mgxClient";
import { Loader2, AlertTriangle, Download, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import html2canvas from "html2canvas";
import AppHeader from "@/components/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";

const client = createClient();

interface ColorPercentages {
  white: number;
  purple: number;
  blue: number;
  light_blue: number;
}

interface PointsBreakdown {
  white: number;
  purple: number;
  blue: number;
  light_blue: number;
}

interface ToothResult {
  missing: boolean;
  white?: number;
  purple?: number;
  blue?: number;
  light_blue?: number;
  total_points?: number;
  pollution_percentage: number;
}

interface AnalysisData {
  has_teeth?: boolean;
  color_percentages?: ColorPercentages;
  points_breakdown?: PointsBreakdown;
  total_points?: number;
  max_points?: number;
  pollution_percentage?: number;
  cleanliness_percentage?: number;
  risk_level?: string;
  hygiene_level?: string;
  teeth?: Record<string, ToothResult>;
  recommendations?: string[];
  // Legacy fields
  php_index?: number;
  plaque_percentage?: number;
}

interface ReportData {
  id: number;
  php_index?: number;
  hygiene_level?: string;
  plaque_percentage?: number;
  risk_level?: string;
  recommendations?: string[];
  image_data?: string;
  created_at?: string;
  analysis_type?: string;
  analysis_data?: AnalysisData;
}

function ExtendedRecommendations({ reportId, lang, t }: { reportId: number; lang: string; t: (key: string) => string }) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [extRecs, setExtRecs] = useState<string[] | null>(null);
  const [orthodonticDetected, setOrthodonticDetected] = useState(false);
  const [orthodonticType, setOrthodonticType] = useState<string | null>(null);

  const fetchExtendedRecs = async () => {
    if (extRecs) {
      setExpanded(!expanded);
      return;
    }
    setLoading(true);
    setExpanded(true);
    try {
      const response = await client.apiCall.invoke({
        url: "/api/v1/analysis/extended-recommendations",
        method: "POST",
        data: { report_id: reportId, lang },
      });
      const data = response?.data ?? response;
      setExtRecs(data.recommendations || []);
      setOrthodonticDetected(data.orthodontic_detected || false);
      setOrthodonticType(data.orthodontic_type || null);
    } catch (err) {
      console.error("Extended recs error:", err);
      setExtRecs([
        lang === "ru" ? "Не удалось загрузить расширенные рекомендации. Попробуйте позже." : "Failed to load extended recommendations. Try again later.",
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mb-4 sm:mb-6">
      <Button
        onClick={fetchExtendedRecs}
        disabled={loading}
        variant="outline"
        className="w-full py-3 text-sm sm:text-base rounded-xl border-purple-300 dark:border-purple-700 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30"
      >
        {loading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t("extended_recs_loading")}
          </>
        ) : (
          <>
            <Sparkles className="mr-2 h-4 w-4" />
            {t("extended_recommendations")}
            {expanded ? <ChevronUp className="ml-2 h-4 w-4" /> : <ChevronDown className="ml-2 h-4 w-4" />}
          </>
        )}
      </Button>

      {expanded && extRecs && (
        <div className="mt-3 space-y-2 animate-in slide-in-from-top-2">
          {orthodonticDetected && (
            <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800">
              <p className="text-sm font-semibold text-blue-800 dark:text-blue-300">
                🦷 {t("orthodontic_detected")}
              </p>
              {orthodonticType && (
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  {t("orthodontic_type")}: {orthodonticType}
                </p>
              )}
            </div>
          )}
          {extRecs.map((rec, idx) => (
            <div key={idx} className="p-2.5 sm:p-3 rounded-lg bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/30 dark:to-indigo-900/30 border border-purple-100 dark:border-purple-800">
              <p className="text-xs sm:text-sm text-purple-800 dark:text-purple-300">
                <span className="font-semibold mr-1">{idx + 1}.</span>
                {rec}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SharedReport() {
  const { reportId } = useParams<{ reportId: string }>();
  const navigate = useNavigate();
  const { t, lang } = useLanguage();
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const response = await client.apiCall.invoke({
          url: `/api/v1/reports/${reportId}`,
          method: "GET",
          data: {},
        });
        const data = response?.data ?? response;
        setReport(data);
      } catch (err: unknown) {
        const error = err as Record<string, unknown>;
        const data = error?.data as Record<string, unknown> | undefined;
        const response = error?.response as Record<string, unknown> | undefined;
        const responseData = response?.data as Record<string, unknown> | undefined;
        const detail =
          (data?.detail as string) ||
          (responseData?.detail as string) ||
          (error?.message as string) ||
          t("report_not_found");
        setError(detail);
      } finally {
        setLoading(false);
      }
    };

    if (reportId) {
      fetchReport();
    }
  }, [reportId]);

  const handleDownload = async () => {
    if (!reportRef.current) return;
    setDownloading(true);
    try {
      const canvas = await html2canvas(reportRef.current, {
        backgroundColor: "#ffffff",
        scale: 2,
        useCORS: true,
        logging: false,
      });
      const link = document.createElement("a");
      link.download = `zubchek-report-${report?.created_at?.slice(0, 10) || new Date().toISOString().slice(0, 10)}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch (err) {
      console.error("Download error:", err);
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col items-center justify-center p-4">
        <Loader2 className="h-12 w-12 text-purple-600 animate-spin mb-4" />
        <p className="text-base text-gray-600 dark:text-gray-300">{t("report_loading")}</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col items-center justify-center p-4 sm:p-6">
        <AlertTriangle className="h-12 w-12 sm:h-16 sm:w-16 text-yellow-500 mb-4" />
        <p className="text-base sm:text-lg text-gray-600 dark:text-gray-300 mb-4">
          {error || t("report_not_found")}
        </p>
        <Button onClick={() => navigate("/")} variant="outline">
          {t("return_home")}
        </Button>
      </div>
    );
  }

  // Extract data from analysis_data or top-level fields
  const ad = report.analysis_data;

  let pollutionPct: number;
  let cleanlinessStr: number;
  let riskLevel: string;
  let colors: ColorPercentages | undefined;
  let points: PointsBreakdown | undefined;
  let totalPoints: number;
  let teeth: Record<string, ToothResult> | undefined;
  let recommendations: string[] | undefined;

  if (ad && ad.color_percentages) {
    colors = ad.color_percentages;
    points = ad.points_breakdown;
    totalPoints = ad.total_points ?? 0;
    pollutionPct = ad.pollution_percentage ?? report.plaque_percentage ?? 0;
    cleanlinessStr = ad.cleanliness_percentage ?? (100 - pollutionPct);
    riskLevel = ad.risk_level || report.risk_level || "low";
    teeth = ad.teeth;
    recommendations = ad.recommendations || report.recommendations;
  } else {
    pollutionPct = report.plaque_percentage ?? 0;
    cleanlinessStr = 100 - pollutionPct;
    riskLevel = report.risk_level || "low";
    totalPoints = 0;
    recommendations = report.recommendations;
  }

  const createdDate = report.created_at
    ? new Date(report.created_at).toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : new Date().toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
        day: "numeric",
        month: "long",
        year: "numeric",
      });



  const quadrants = [
    { label: lang === "ru" ? "Квадрант 1" : "Quadrant 1", teeth: ["1.1", "1.2", "1.3"] },
    { label: lang === "ru" ? "Квадрант 2" : "Quadrant 2", teeth: ["2.1", "2.2", "2.3"] },
    { label: lang === "ru" ? "Квадрант 3" : "Quadrant 3", teeth: ["3.1", "3.2", "3.3"] },
    { label: lang === "ru" ? "Квадрант 4" : "Quadrant 4", teeth: ["4.1", "4.2", "4.3"] },
  ];

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col">
      {/* Header */}
      <AppHeader showBack />

      {/* Content */}
      <main className="flex-1 px-4 sm:px-6 lg:px-8 py-4 sm:py-6 max-w-lg lg:max-w-4xl mx-auto w-full">
        <div ref={reportRef} className="bg-white dark:bg-gray-900 p-4 sm:p-6">
          <h2 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white mb-4 sm:mb-6">
            {createdDate}
          </h2>

          {report.image_data && (
            <div className="flex justify-center mb-4 sm:mb-6">
              <img
                src={report.image_data}
                alt="Teeth photo"
                className="w-48 h-36 sm:w-64 sm:h-48 object-cover rounded-xl border border-gray-200 dark:border-gray-700"
              />
            </div>
          )}

          <h3 className="text-lg sm:text-xl font-semibold text-gray-800 dark:text-gray-100 mb-3 sm:mb-4">
            {lang === "ru" ? "Индекс Z — Результат" : "Z-Index — Result"}
          </h3>

          {/* Main pollution indicator */}
          <div className="mb-5 sm:mb-6 p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/30 dark:to-purple-800/20 border border-purple-200 dark:border-purple-700">
            <div className="text-center">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                {lang === "ru" ? "Индекс налёта:" : "Dental plaque index:"}
              </p>
              <p className="text-4xl sm:text-5xl font-bold text-purple-700 dark:text-purple-300">
                {pollutionPct}%
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {lang === "ru" ? `Чистота: ${cleanlinessStr}%` : `Cleanliness: ${cleanlinessStr}%`}
              </p>
            </div>

            <div className="flex justify-center mt-3">
              <span className={`px-4 py-1.5 rounded-full text-sm font-semibold ${
                riskLevel === "high"
                  ? "bg-red-500 text-white"
                  : riskLevel === "medium"
                  ? "bg-yellow-500 text-white"
                  : "bg-green-500 text-white"
              }`}>
                {riskLevel === "high"
                  ? (lang === "ru" ? "Высокий индекс налёта" : "High dental plaque")
                  : riskLevel === "medium"
                  ? (lang === "ru" ? "Средний индекс налёта" : "Medium dental plaque")
                  : (lang === "ru" ? "Низкий индекс налёта" : "Low dental plaque")}
              </span>
            </div>
          </div>



          {/* Per-tooth details */}
          {teeth && (
            <div className="mb-5 sm:mb-6">
              <h4 className="text-base sm:text-lg font-semibold text-gray-800 dark:text-gray-100 mb-3">
                {lang === "ru" ? "Детализация по зубам" : "Per-tooth details"}
              </h4>

              <div className="space-y-4">
                {quadrants.map((quadrant) => (
                  <div key={quadrant.label}>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                      {quadrant.label}
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                      {quadrant.teeth.map((toothKey) => {
                        const tooth = teeth[toothKey];
                        if (!tooth) return null;

                        if (tooth.missing) {
                          return (
                            <div key={toothKey} className="p-2.5 sm:p-3 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50 text-center">
                              <div className="text-sm font-bold text-gray-400 dark:text-gray-500">{toothKey}</div>
                              <div className="text-[10px] sm:text-xs text-gray-400 dark:text-gray-500 mt-1">
                                {lang === "ru" ? "отсутствует" : "missing"}
                              </div>
                            </div>
                          );
                        }

                        const pct = tooth.pollution_percentage;
                        const bgColor = pct <= 30
                          ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
                          : pct <= 60
                          ? "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800"
                          : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800";
                        const textColor = pct <= 30
                          ? "text-green-700 dark:text-green-400"
                          : pct <= 60
                          ? "text-yellow-700 dark:text-yellow-400"
                          : "text-red-700 dark:text-red-400";

                        return (
                          <div key={toothKey} className={`p-2.5 sm:p-3 rounded-lg border ${bgColor} text-center`}>
                            <div className="text-sm font-bold text-gray-700 dark:text-gray-300">{toothKey}</div>
                            <div className={`text-lg sm:text-xl font-bold ${textColor} mt-0.5`}>
                              {pct}%
                            </div>
                            <div className="text-[10px] text-gray-400 dark:text-gray-500">
                              {lang === "ru" ? "налёт" : "plaque"}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}



          {/* Recommendations */}
          {recommendations && recommendations.length > 0 && (
            <div className="mb-4 sm:mb-6">
              <h4 className="text-base sm:text-lg font-medium text-gray-700 dark:text-gray-200 mb-2 sm:mb-3">
                {t("recommendations")}
              </h4>
              <div className="space-y-2">
                {recommendations.map((rec, idx) => (
                  <div key={idx} className="p-2.5 sm:p-3 rounded-lg bg-purple-50 dark:bg-purple-900/30 border border-purple-100 dark:border-purple-800">
                    <p className="text-xs sm:text-sm text-purple-800 dark:text-purple-300">{rec}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Extended Recommendations */}
          {report && report.id && (
            <ExtendedRecommendations reportId={report.id} lang={lang} t={t} />
          )}

          <div className="pt-3 mt-3 border-t border-gray-100 dark:border-gray-800 text-center">
            <span className="text-xs text-gray-400">{t("branding_footer")}</span>
          </div>
        </div>

        <div className="flex flex-col gap-3 mt-4 sm:mt-6">
          <Button
            onClick={handleDownload}
            disabled={downloading}
            className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 sm:py-6 text-base sm:text-lg rounded-xl"
          >
            <Download className="mr-2 h-5 w-5" />
            {downloading ? t("creating_file") : t("download_report")}
          </Button>
          <Button
            onClick={() => navigate("/")}
            variant="outline"
            className="w-full py-5 sm:py-6 text-base sm:text-lg rounded-xl border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            {t("new_analysis")}
          </Button>
        </div>
      </main>
    </div>
  );
}