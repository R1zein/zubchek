import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Loader2,
  FileText,
  ChevronRight,
} from "lucide-react";
import { getSession, logout as customLogout, client } from "@/lib/auth";
import AppHeader from "@/components/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { formatAge } from "@/lib/formatAge";

interface Report {
  id: number;
  php_index: number | null;
  hygiene_level: string | null;
  plaque_percentage: number | null;
  risk_level: string | null;
  image_data: string | null;
  created_at: string | null;
}

export default function PatientDashboard() {
  const [loading, setLoading] = useState(true);
  const [reports, setReports] = useState<Report[]>([]);
  const [profileName, setProfileName] = useState("");
  const [birthDate, setBirthDate] = useState<string | null>(null);
  const navigate = useNavigate();
  const { t, lang } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const session = getSession();
      if (!session || session.role !== "patient") {
        navigate("/");
        return;
      }
      setProfileName(session.full_name || "");
      setBirthDate(session.birth_date || null);

      try {
        const reportsRes = await client.apiCall.invoke({
          url: `/api/v1/invite/my-reports?current_user_id=${encodeURIComponent(session.user_id)}`,
          method: "GET",
          data: {},
        });
        setReports(reportsRes?.data?.reports || []);
      } catch (err: unknown) {
        console.error("Failed to load reports:", err);
        setReports([]);
      }
    } catch (err: unknown) {
      console.error("Load error:", err);
      navigate("/");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    customLogout();
    navigate("/");
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex items-center justify-center">
        <Loader2 className="h-10 w-10 text-purple-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col">
      <AppHeader
        showLogout
        onLogout={handleLogout}
        userName={profileName || undefined}
        badge={{ label: t("patient_label"), color: "bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300" }}
        extraInfo={birthDate ? formatAge(birthDate, lang) : undefined}
      />

      <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 max-w-3xl lg:max-w-5xl mx-auto w-full">
        <div className="bg-white dark:bg-gray-800 p-5 rounded-xl border border-gray-100 dark:border-gray-700">
          <h3 className="font-semibold text-gray-800 dark:text-gray-100 mb-3 flex items-center gap-2">
            <FileText className="h-5 w-5 text-purple-600 dark:text-purple-400" />
            {t("my_reports")} ({reports.length})
          </h3>

          {reports.length === 0 ? (
            <div className="text-center py-6 text-gray-500 dark:text-gray-400">
              <FileText className="h-10 w-10 mx-auto mb-2 text-gray-300 dark:text-gray-600" />
              <p className="text-sm">{t("no_reports_patient")}</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                {t("doctor_will_add")}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {reports.map((report) => (
                <button
                  key={report.id}
                  onClick={() => navigate(`/report/${report.id}`)}
                  className="w-full text-left p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 border border-gray-100 dark:border-gray-600 flex items-center justify-between transition-colors"
                >
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {report.created_at
                        ? new Date(report.created_at).toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
                            day: "numeric",
                            month: "long",
                            year: "numeric",
                          })
                        : t("date_unknown")}
                    </p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {lang === "ru" ? "Загрязнение" : "Pollution"}: {report.plaque_percentage ?? "—"}%
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          report.risk_level === "high"
                            ? "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300"
                            : report.risk_level === "medium"
                            ? "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300"
                            : "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
                        }`}
                      >
                        {report.risk_level === "high"
                          ? t("high_risk")
                          : report.risk_level === "medium"
                          ? t("medium_risk")
                          : t("low_risk")}
                      </span>
                    </div>
                  </div>
                  <ChevronRight className="h-5 w-5 text-gray-300 dark:text-gray-600" />
                </button>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}