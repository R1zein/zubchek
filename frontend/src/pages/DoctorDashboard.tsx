import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Users,
  FileText,
  ChevronRight,
  Loader2,
  Camera,
  ArrowLeft,
  Trash2,
  X,
  UserPlus,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { getSession, logout as customLogout, client } from "@/lib/auth";
import AppHeader from "@/components/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { formatAge } from "@/lib/formatAge";

interface Patient {
  patient_id: string;
  full_name: string | null;
  phone: string | null;
  birth_date: string | null;
  gender: string | null;
  email: string | null;
}

interface Report {
  id: number;
  php_index: number | null;
  hygiene_level: string | null;
  plaque_percentage: number | null;
  risk_level: string | null;
  created_at: string | null;
}

function formatDoctorName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0];
  const surname = parts[0];
  const initials = parts
    .slice(1)
    .map((p) => p.charAt(0).toUpperCase() + ".")
    .join("");
  return `${surname} ${initials}`;
}

export default function DoctorDashboard() {
  const [loading, setLoading] = useState(true);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [patientReports, setPatientReports] = useState<Report[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [profileName, setProfileName] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [newPatientSurname, setNewPatientSurname] = useState("");
  const [newPatientFirstName, setNewPatientFirstName] = useState("");
  const [newPatientGender, setNewPatientGender] = useState<string>("");
  const [newPatientBirthDate, setNewPatientBirthDate] = useState<string>("");
  const [newPatientEmail, setNewPatientEmail] = useState<string>("");
  const [registeringPatient, setRegisteringPatient] = useState(false);
  const [deletingPatient, setDeletingPatient] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t, lang } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const session = getSession();
      if (!session || session.role !== "doctor") {
        navigate("/");
        return;
      }
      setProfileName(session.full_name || "");

      const patientsRes = await client.apiCall.invoke({
        url: `/api/v1/invite/my-patients?current_user_id=${encodeURIComponent(session.user_id)}`,
        method: "GET",
        data: {},
      });
      setPatients(patientsRes?.data?.patients || []);
    } catch (err: unknown) {
      console.error("Load error:", err);
      navigate("/");
    } finally {
      setLoading(false);
    }
  };

  const viewPatientReports = async (patient: Patient) => {
    const session = getSession();
    if (!session) return;
    setSelectedPatient(patient);
    setLoadingReports(true);
    try {
      const res = await client.apiCall.invoke({
        url: `/api/v1/invite/patient-reports/${patient.patient_id}?current_user_id=${encodeURIComponent(session.user_id)}`,
        method: "GET",
        data: {},
      });
      setPatientReports(res?.data?.reports || []);
    } catch {
      setPatientReports([]);
    } finally {
      setLoadingReports(false);
    }
  };

  const handleDeleteReport = async (reportId: number) => {
    const session = getSession();
    if (!session) return;
    const confirmMsg = lang === "ru" ? "Удалить этот отчёт? Это действие нельзя отменить." : "Delete this report? This action cannot be undone.";
    if (!window.confirm(confirmMsg)) return;
    try {
      await client.apiCall.invoke({
        url: `/api/v1/invite/delete-report/${reportId}?current_user_id=${encodeURIComponent(session.user_id)}`,
        method: "DELETE",
        data: {},
      });
      setPatientReports((prev) => prev.filter((r) => r.id !== reportId));
      toast({
        title: lang === "ru" ? "Отчёт удалён" : "Report deleted",
      });
    } catch {
      toast({
        title: lang === "ru" ? "Ошибка удаления" : "Delete failed",
        variant: "destructive",
      });
    }
  };

  const handleLogout = () => {
    customLogout();
    navigate("/");
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast({ title: t("error"), description: t("select_image"), variant: "destructive" });
      return;
    }

    const reader = new FileReader();
    reader.onload = async () => {
      const imageDataUri = reader.result as string;
      await analyzeImage(imageDataUri);
    };
    reader.readAsDataURL(file);
  };

  const analyzeImage = async (imageDataUri: string) => {
    const session = getSession();
    if (!session || !selectedPatient) return;
    setIsAnalyzing(true);
    try {
      const url = `/api/v1/analysis/analyze?current_user_id=${encodeURIComponent(session.user_id)}`;
      const response = await client.apiCall.invoke({
        url,
        method: "POST",
        data: { image: imageDataUri, birth_date: selectedPatient.birth_date || undefined },
        options: { timeout: 600_000 },
      });

      const result = response?.data ?? response;

      if (result.error === "no_teeth") {
        toast({ title: t("teeth_not_found"), description: result.message || "", variant: "destructive" });
        setIsAnalyzing(false);
        return;
      }

      if (result.error === "no_dye_detected") {
        toast({ title: t("dye_not_detected"), description: result.message || "", variant: "destructive" });
        setIsAnalyzing(false);
        return;
      }

      if (!result.has_teeth && result.error) {
        toast({ title: t("analysis_error"), description: result.message || "", variant: "destructive" });
        setIsAnalyzing(false);
        return;
      }

      if (result.report_id) {
        try {
          await client.apiCall.invoke({
            url: `/api/v1/invite/assign-report?current_user_id=${encodeURIComponent(session.user_id)}`,
            method: "POST",
            data: {
              report_id: result.report_id,
              patient_id: selectedPatient.patient_id,
            },
          });
        } catch (err) {
          console.error("Failed to assign report:", err);
        }
      }

      navigate("/results", {
        state: {
          analysisResult: result,
          imageDataUri,
          assignedPatient: {
            id: selectedPatient.patient_id,
            name: selectedPatient.full_name,
            email: selectedPatient.email,
          },
        },
      });
    } catch (err: unknown) {
      const error = err as Record<string, unknown>;
      const data = error?.data as Record<string, unknown> | undefined;
      const detail = (data?.detail as string) || (error?.message as string) || t("analysis_error_retry");
      toast({ title: t("error"), description: detail, variant: "destructive" });
    } finally {
      setIsAnalyzing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const openRegisterModal = () => {
    setNewPatientSurname("");
    setNewPatientFirstName("");
    setNewPatientGender("");
    setNewPatientBirthDate("");
    setNewPatientEmail("");
    setShowRegisterModal(true);
  };

  const registerNewPatient = async () => {
    const session = getSession();
    if (!session) return;
    if (!newPatientSurname.trim()) {
      toast({ title: t("error"), description: t("enter_patient_name"), variant: "destructive" });
      return;
    }
    if (!newPatientBirthDate) {
      toast({ title: t("error"), description: t("birth_date_required"), variant: "destructive" });
      return;
    }
    const emailTrimmed = newPatientEmail.trim();
    if (emailTrimmed && !emailTrimmed.includes("@")) {
      toast({ title: t("error"), description: t("enter_email"), variant: "destructive" });
      return;
    }
    const fullName = [newPatientSurname.trim(), newPatientFirstName.trim()].filter(Boolean).join(" ");
    setRegisteringPatient(true);
    try {
      const res = await client.apiCall.invoke({
        url: `/api/v1/invite/register-patient?current_user_id=${encodeURIComponent(session.user_id)}`,
        method: "POST",
        data: {
          full_name: fullName,
          email: emailTrimmed || null,
          birth_date: newPatientBirthDate || null,
          gender: newPatientGender || null,
        },
      });
      const newPatient: Patient = {
        patient_id: res?.data?.patient_id || "",
        full_name: fullName,
        phone: null,
        birth_date: newPatientBirthDate || null,
        gender: newPatientGender || null,
        email: emailTrimmed || null,
      };
      setPatients((prev) => [...prev, newPatient]);
      setShowRegisterModal(false);
      toast({
        title: t("patient_registered"),
        description: newPatient.full_name || "",
      });
    } catch (err: unknown) {
      const error = err as Record<string, unknown>;
      const data = error?.data as Record<string, unknown> | undefined;
      const detail = (data?.detail as string) || (error?.message as string) || t("registration_error");
      toast({ title: t("error"), description: detail, variant: "destructive" });
    } finally {
      setRegisteringPatient(false);
    }
  };

  const deletePatient = async () => {
    const session = getSession();
    if (!session || !selectedPatient) return;
    setDeletingPatient(true);
    try {
      await client.apiCall.invoke({
        url: `/api/v1/invite/delete-patient/${selectedPatient.patient_id}?current_user_id=${encodeURIComponent(session.user_id)}`,
        method: "DELETE",
        data: {},
      });
      setPatients((prev) => prev.filter((p) => p.patient_id !== selectedPatient.patient_id));
      setSelectedPatient(null);
      setPatientReports([]);
      setShowDeleteConfirm(false);
      toast({ title: t("deleted"), description: t("patient_data_deleted") });
    } catch (err: unknown) {
      const error = err as Record<string, unknown>;
      const data = error?.data as Record<string, unknown> | undefined;
      const detail = (data?.detail as string) || (error?.message as string) || t("deletion_error");
      toast({ title: t("error"), description: detail, variant: "destructive" });
    } finally {
      setDeletingPatient(false);
    }
  };

  // Filter patients by search query
  const filteredPatients = patients.filter((p) => {
    if (!searchQuery.trim()) return true;
    const name = (p.full_name || "").toLowerCase();
    return name.includes(searchQuery.toLowerCase().trim());
  });

  // Format birth date for table display
  const formatBirthDate = (dateStr: string | null): string => {
    if (!dateStr) return "—";
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", { day: "2-digit", month: "2-digit", year: "numeric" });
    } catch {
      return dateStr;
    }
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
        userName={profileName ? formatDoctorName(profileName) : undefined}
      />

      <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 w-full">
        {/* Analyzing state */}
        {isAnalyzing && (
          <div className="flex flex-col items-center justify-center py-16">
            <Loader2 className="h-12 w-12 text-purple-600 animate-spin mb-4" />
            <p className="text-lg text-gray-600 dark:text-gray-300">{t("analyzing")}</p>
            <p className="text-sm text-gray-400 mt-1">{t("analyzing_wait")}</p>
          </div>
        )}

        {/* Patient detail view */}
        {selectedPatient && !isAnalyzing && (
          <div>
            <button
              onClick={() => { setSelectedPatient(null); setPatientReports([]); }}
              className="text-purple-600 dark:text-purple-400 text-sm mb-4 flex items-center gap-1 hover:underline"
            >
              <ArrowLeft className="h-4 w-4" />
              {t("back_to_patients")}
            </button>

            <div className="mb-4">
              <h2 className="text-xl font-bold text-gray-800 dark:text-white">
                {selectedPatient.full_name || t("patient_label")}
              </h2>
              <div className="flex items-center gap-2 mt-1 text-sm text-gray-500 dark:text-gray-400">
                {selectedPatient.gender && (
                  <span className="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded text-xs">
                    {selectedPatient.gender === "male" ? t("male") : t("female")}
                  </span>
                )}
                {selectedPatient.birth_date && (
                  <span className="text-xs">{formatAge(selectedPatient.birth_date, lang)}</span>
                )}
              </div>
            </div>

            <Button
              onClick={handleFileSelect}
              className="bg-purple-600 hover:bg-purple-700 text-white w-full py-5 text-base rounded-xl mb-6"
            >
              <Camera className="mr-2 h-5 w-5" />
              {t("add_photo")}
            </Button>
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />

            {loadingReports ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 text-purple-600 animate-spin" />
              </div>
            ) : patientReports.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <FileText className="h-12 w-12 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
                <p>{t("no_reports_yet")}</p>
                <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">{t("add_photo_first")}</p>
              </div>
            ) : (
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-700 dark:text-gray-200 flex items-center gap-2">
                  <FileText className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                  {t("reports")} ({patientReports.length})
                </h3>
                {patientReports.map((report) => (
                  <div
                    key={report.id}
                    className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-100 dark:border-gray-700 hover:border-purple-200 dark:hover:border-purple-600 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div
                        className="flex-1 cursor-pointer"
                        onClick={() => navigate(`/report/${report.id}`)}
                      >
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {report.created_at
                            ? new Date(report.created_at).toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", { day: "numeric", month: "long", year: "numeric" })
                            : t("date_unknown")}
                        </p>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                            {lang === "ru" ? "Индекс налёта" : "Dental plaque"}: {report.plaque_percentage ?? "—"}%
                          </span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${report.risk_level === "high" ? "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300" : report.risk_level === "medium" ? "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300" : "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"}`}>
                            {report.risk_level === "high" ? t("high_risk") : report.risk_level === "medium" ? t("medium_risk") : t("low_risk")}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteReport(report.id);
                          }}
                          className="p-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                          title={lang === "ru" ? "Удалить отчёт" : "Delete report"}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                        <ChevronRight
                          className="h-5 w-5 text-gray-300 dark:text-gray-600 cursor-pointer"
                          onClick={() => navigate(`/report/${report.id}`)}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Delete patient */}
            <div className="mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
              {!showDeleteConfirm ? (
                <Button onClick={() => setShowDeleteConfirm(true)} variant="outline" className="w-full border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">
                  <Trash2 className="mr-2 h-4 w-4" />
                  {t("delete_patient")}
                </Button>
              ) : (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4">
                  <p className="text-sm text-red-700 dark:text-red-300 font-medium mb-3">{t("delete_confirm")}</p>
                  <div className="flex gap-2">
                    <Button onClick={deletePatient} disabled={deletingPatient} className="flex-1 bg-red-600 hover:bg-red-700 text-white">
                      {deletingPatient ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                      {t("yes_delete")}
                    </Button>
                    <Button onClick={() => setShowDeleteConfirm(false)} variant="outline" className="flex-1">
                      {t("cancel")}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Main dashboard - Table view */}
        {!selectedPatient && !isAnalyzing && (
          <>
            {/* Top bar: title + add patient button */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <h2 className="text-xl font-bold text-gray-800 dark:text-white flex items-center gap-2">
                <Users className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                {t("my_patients")}
                <span className="text-sm font-normal text-gray-400 ml-1">({patients.length})</span>
              </h2>
              <Button onClick={openRegisterModal} className="bg-purple-600 hover:bg-purple-700 text-white text-sm sm:text-base px-3 sm:px-4 py-2 w-full sm:w-auto shrink-0">
                <UserPlus className="mr-2 h-4 w-4" />
                {t("register_patient")}
              </Button>
            </div>

            {/* Search bar */}
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={lang === "ru" ? "Поиск по имени пациента..." : "Search by patient name..."}
                className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-200"
              />
            </div>

            {/* Patients table */}
            {patients.length === 0 ? (
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 text-center py-12">
                <Users className="h-12 w-12 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
                <p className="text-gray-500 dark:text-gray-400">{t("no_patients_yet")}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{t("register_patient_hint")}</p>
              </div>
            ) : (
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                {/* Table header */}
                <div className="grid grid-cols-[1fr_auto_auto] sm:grid-cols-[2fr_1fr_1fr] gap-2 px-4 py-3 bg-gray-50 dark:bg-gray-750 border-b border-gray-200 dark:border-gray-700 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  <div>{lang === "ru" ? "Имя" : "Name"}</div>
                  <div className="text-center">{lang === "ru" ? "Дата рождения" : "Birth date"}</div>
                  <div className="text-right">{lang === "ru" ? "Возраст" : "Age"}</div>
                </div>

                {/* Table rows */}
                {filteredPatients.length === 0 ? (
                  <div className="px-4 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
                    {lang === "ru" ? "Пациенты не найдены" : "No patients found"}
                  </div>
                ) : (
                  <div className="divide-y divide-gray-100 dark:divide-gray-700">
                    {filteredPatients.map((patient) => (
                      <button
                        key={patient.patient_id}
                        onClick={() => viewPatientReports(patient)}
                        className="w-full grid grid-cols-[1fr_auto_auto] sm:grid-cols-[2fr_1fr_1fr] gap-2 px-4 py-3 text-left hover:bg-purple-50 dark:hover:bg-purple-900/10 transition-colors items-center"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <div className="w-8 h-8 rounded-full bg-purple-100 dark:bg-purple-900/40 flex items-center justify-center flex-shrink-0">
                            <span className="text-xs font-bold text-purple-700 dark:text-purple-300">
                              {(patient.full_name || "?").charAt(0).toUpperCase()}
                            </span>
                          </div>
                          <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                            {patient.full_name || t("patient_label")}
                          </span>
                        </div>
                        <div className="text-center text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
                          {formatBirthDate(patient.birth_date)}
                        </div>
                        <div className="text-right text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
                          {patient.birth_date ? formatAge(patient.birth_date, lang) : "—"}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>

      {/* Register Patient Modal */}
      {showRegisterModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md shadow-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white">{t("new_patient")}</h3>
              <button onClick={() => setShowRegisterModal(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4 max-h-[70vh] overflow-y-auto">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 block">{t("patient_surname")} *</label>
                <input
                  type="text"
                  value={newPatientSurname}
                  onChange={(e) => setNewPatientSurname(e.target.value)}
                  placeholder={t("patient_surname_placeholder")}
                  className="w-full border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-200"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 block">{t("patient_firstname")} *</label>
                <input
                  type="text"
                  value={newPatientFirstName}
                  onChange={(e) => setNewPatientFirstName(e.target.value)}
                  placeholder={t("patient_firstname_placeholder")}
                  className="w-full border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-200"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 block">{t("gender")}</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setNewPatientGender("male")}
                    autoComplete="off"
                    className={`flex-1 py-2.5 rounded-lg text-sm font-medium border transition-colors ${newPatientGender === "male" ? "bg-purple-100 dark:bg-purple-900/50 border-purple-300 dark:border-purple-600 text-purple-700 dark:text-purple-300" : "bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600"}`}
                  >
                    Мужской
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewPatientGender("female")}
                    autoComplete="off"
                    className={`flex-1 py-2.5 rounded-lg text-sm font-medium border transition-colors ${newPatientGender === "female" ? "bg-purple-100 dark:bg-purple-900/50 border-purple-300 dark:border-purple-600 text-purple-700 dark:text-purple-300" : "bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600"}`}
                  >
                    Женский
                  </button>
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 block">{t("birth_date")} <span className="text-black dark:text-white">*</span></label>
                <input
                  type="date"
                  required
                  value={newPatientBirthDate}
                  onChange={(e) => setNewPatientBirthDate(e.target.value)}
                  className="w-full border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-200"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 block">{t("patient_email_optional")}</label>
                <input
                  type="email"
                  value={newPatientEmail}
                  onChange={(e) => setNewPatientEmail(e.target.value)}
                  placeholder={t("email_placeholder")}
                  className="w-full border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-200"
                />
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">{t("patient_email_hint")}</p>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-gray-100 dark:border-gray-700 flex gap-2">
              <Button onClick={registerNewPatient} disabled={registeringPatient || !newPatientSurname.trim()} className="flex-1 bg-purple-600 hover:bg-purple-700 text-white py-2.5">
                {registeringPatient ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <UserPlus className="mr-2 h-4 w-4" />}
                {t("register")}
              </Button>
              <Button onClick={() => setShowRegisterModal(false)} variant="outline" className="px-6">
                {t("cancel")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}