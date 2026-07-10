import { useRef, useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, Download, FileText, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getSession, client } from "@/lib/auth";
import AppHeader from "@/components/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";

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

interface AnalysisResult {
  has_teeth: boolean;
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
  orthodontic_detected?: boolean;
  orthodontic_type?: string | null;
  report_id?: number;
  error?: string;
  message?: string;
  // Legacy compat
  plaque_percentage?: number;
}

export default function Results() {
  const location = useLocation();
  const navigate = useNavigate();
  const reportRef = useRef<HTMLDivElement>(null);
  const page1Ref = useRef<HTMLDivElement>(null);
  const page2Ref = useRef<HTMLDivElement>(null);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const { t, lang } = useLanguage();
  const { analysisResult, imageDataUri, assignedPatient } = (location.state as {
    analysisResult: AnalysisResult;
    imageDataUri: string;
    assignedPatient?: { id: string; name: string } | null;
  }) || {};

  useEffect(() => {
    const assignReport = async () => {
      if (!assignedPatient || !analysisResult?.report_id) return;
      const session = getSession();
      if (!session || session.role !== "doctor") return;

      try {
        await client.apiCall.invoke({
          url: `/api/v1/invite/assign-report?current_user_id=${encodeURIComponent(session.user_id)}`,
          method: "POST",
          data: {
            report_id: analysisResult.report_id,
            patient_id: assignedPatient.id,
          },
        });
      } catch (err) {
        console.error("Failed to assign report to patient:", err);
      }
    };
    assignReport();
  }, [assignedPatient, analysisResult?.report_id]);

  // Render a DOM element to a canvas in the LIGHT theme (so the export isn't
  // dark), restoring the theme afterwards. html2canvas is imported lazily so it
  // never runs during the blog prerender and stays out of the initial bundle.
  const captureToCanvas = async (el: HTMLElement) => {
    const html2canvas = (await import("html2canvas")).default;
    const root = document.documentElement;
    const wasDark = root.classList.contains("dark");
    if (wasDark) root.classList.remove("dark");
    try {
      return await html2canvas(el, {
        backgroundColor: "#ffffff",
        scale: 2,
        useCORS: true,
        logging: false,
      });
    } finally {
      if (wasDark) root.classList.add("dark");
    }
  };

  const fileStamp = () => new Date().toISOString().slice(0, 10);

  // PNG: the whole report as one image.
  const handlePng = async () => {
    setDownloadOpen(false);
    if (!reportRef.current) return;
    const canvas = await captureToCanvas(reportRef.current);
    const link = document.createElement("a");
    link.download = `zubchek-report-${fileStamp()}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  };

  // PDF: exactly two A4 pages — page 1 = index + per-tooth, page 2 = recommendations.
  // Each section is scaled to fit within its page.
  const handlePdf = async () => {
    setDownloadOpen(false);
    if (!page1Ref.current) return;
    const { jsPDF } = await import("jspdf");
    const pdf = new jsPDF({ unit: "mm", format: "a4" });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const margin = 10;
    const maxW = pageW - margin * 2;
    const maxH = pageH - margin * 2;

    const addSection = async (el: HTMLElement, isFirst: boolean) => {
      const canvas = await captureToCanvas(el);
      let w = maxW;
      let h = (canvas.height * w) / canvas.width;
      if (h > maxH) {
        h = maxH;
        w = (canvas.width * h) / canvas.height;
      }
      const x = margin + (maxW - w) / 2;
      if (!isFirst) pdf.addPage();
      pdf.addImage(canvas.toDataURL("image/png"), "PNG", x, margin, w, h);
    };

    await addSection(page1Ref.current, true);
    if (page2Ref.current) await addSection(page2Ref.current, false);
    pdf.save(`zubchek-report-${fileStamp()}.pdf`);
  };

  if (!analysisResult) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col items-center justify-center p-4 sm:p-6">
        <AlertTriangle className="h-12 w-12 sm:h-16 sm:w-16 text-yellow-500 mb-4" />
        <p className="text-base sm:text-lg text-gray-600 dark:text-gray-300 mb-4">{t("no_data")}</p>
        <Button onClick={() => navigate("/")} variant="outline">
          {t("return_home")}
        </Button>
      </div>
    );
  }

  const today = new Date();
  const dateStr = today.toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const pollutionPct = analysisResult.pollution_percentage ?? analysisResult.plaque_percentage ?? 0;
  const cleanlinessStr = analysisResult.cleanliness_percentage ?? (100 - pollutionPct);
  const riskLevel = analysisResult.risk_level || "low";
  const teeth = analysisResult.teeth;

  // Quadrant layout for per-tooth display (visual order left-to-right, .1 always on the left)
  const quadrants = [
    { label: lang === "ru" ? "Квадрант 1" : "Quadrant 1", teeth: ["1.1", "1.2", "1.3"] },
    { label: lang === "ru" ? "Квадрант 2" : "Quadrant 2", teeth: ["2.1", "2.2", "2.3"] },
    { label: lang === "ru" ? "Квадрант 3" : "Quadrant 3", teeth: ["3.1", "3.2", "3.3"] },
    { label: lang === "ru" ? "Квадрант 4" : "Quadrant 4", teeth: ["4.1", "4.2", "4.3"] },
  ];

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col">
      {/* Header */}
      <div className="no-print">
        <AppHeader showBack backTo="/" />
      </div>

      {/* Content */}
      <main className="flex-1 px-4 sm:px-6 lg:px-8 py-4 sm:py-6 max-w-lg lg:max-w-4xl mx-auto w-full">
        <div ref={reportRef} id="report-printable" className="bg-white dark:bg-gray-900 p-4 sm:p-6">
          {/* PDF page 1 — general index + per-tooth */}
          <div ref={page1Ref}>
          <h2 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white mb-4 sm:mb-6">{dateStr}</h2>

          {imageDataUri && (
            <div className="flex justify-center mb-4 sm:mb-6">
              <img
                src={imageDataUri}
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

            {/* Risk level badge */}
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



          {/* Orthodontic appliance detected (automatic) */}
          {analysisResult.orthodontic_detected && (
            <div className="mb-4 sm:mb-6 p-3 sm:p-4 rounded-lg bg-sky-50 dark:bg-sky-900/30 border border-sky-200 dark:border-sky-800">
              <p className="text-sm sm:text-base font-medium text-sky-800 dark:text-sky-300">
                🦷 {t("orthodontic_detected")}
              </p>
              {analysisResult.orthodontic_type && (
                <p className="text-xs sm:text-sm text-sky-700 dark:text-sky-400 mt-1">
                  {t("orthodontic_type")}: {analysisResult.orthodontic_type}
                </p>
              )}
            </div>
          )}
          </div>{/* end PDF page 1 */}

          {/* PDF page 2 — recommendations only */}
          <div ref={page2Ref}>
          {/* Recommendations */}
          {analysisResult.recommendations && analysisResult.recommendations.length > 0 && (
            <div className="mb-4 sm:mb-6">
              <h4 className="text-base sm:text-lg font-medium text-gray-700 dark:text-gray-200 mb-2 sm:mb-3">
                {t("recommendations")}
              </h4>
              <div className="space-y-2">
                {analysisResult.recommendations.map((rec, idx) => (
                  <div key={idx} className="p-2.5 sm:p-3 rounded-lg bg-purple-50 dark:bg-purple-900/30 border border-purple-100 dark:border-purple-800">
                    <p className="text-xs sm:text-sm text-purple-800 dark:text-purple-300">{rec}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="pt-3 mt-3 border-t border-gray-100 dark:border-gray-800 text-center">
            <span className="text-xs text-gray-400">{t("branding_footer")}</span>
          </div>
          </div>{/* end PDF page 2 */}
        </div>

        <div className="no-print flex flex-col gap-3 mt-4 sm:mt-6">
          <Button
            onClick={() => setDownloadOpen(true)}
            className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 sm:py-6 text-base sm:text-lg rounded-xl"
          >
            <Download className="mr-2 h-5 w-5" />
            {t("download_report")}
          </Button>
          <Button
            onClick={() => navigate("/")}
            variant="outline"
            className="w-full py-5 sm:py-6 text-base sm:text-lg rounded-xl border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            {t("new_analysis")}
          </Button>
        </div>

        <Dialog open={downloadOpen} onOpenChange={setDownloadOpen}>
          <DialogContent className="sm:max-w-sm">
            <DialogHeader>
              <DialogTitle>{lang === "ru" ? "Скачать отчёт" : "Download report"}</DialogTitle>
            </DialogHeader>
            <div className="flex flex-col gap-3 pt-2">
              <Button
                onClick={handlePdf}
                className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-base rounded-xl"
              >
                <FileText className="mr-2 h-5 w-5" />
                PDF {lang === "ru" ? "(2 страницы)" : "(2 pages)"}
              </Button>
              <Button
                onClick={handlePng}
                variant="outline"
                className="w-full py-5 text-base rounded-xl border-purple-300 dark:border-purple-700 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30"
              >
                <ImageIcon className="mr-2 h-5 w-5" />
                PNG {lang === "ru" ? "(изображение)" : "(image)"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}