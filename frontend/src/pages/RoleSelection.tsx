import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Stethoscope, User, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { getSession, customLogin, customRegister } from "@/lib/auth";
import AppHeader from "@/components/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";

export default function RoleSelection() {
  const [mode, setMode] = useState<"register" | "login">("login");
  const [selectedRole, setSelectedRole] = useState<"doctor" | "patient" | null>(null);
  const [fullName, setFullName] = useState("");
  const [clinicPassword, setClinicPassword] = useState("");
  const [userPassword, setUserPassword] = useState("");
  const [patientLogin, setPatientLogin] = useState("");

  const [saving, setSaving] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t, lang } = useLanguage();

  useEffect(() => {
    const session = getSession();
    if (session) {
      if (session.role === "doctor") {
        navigate("/doctor", { replace: true });
      } else if (session.role === "patient") {
        navigate("/patient", { replace: true });
      }
    }
    setCheckingSession(false);
  }, [navigate]);

  const resetForm = () => {
    setSelectedRole(null);
    setFullName("");
    setClinicPassword("");
    setUserPassword("");
    setPatientLogin("");
  };

  const switchMode = (newMode: "register" | "login") => {
    setMode(newMode);
    resetForm();
  };

  const handleRegister = async () => {
    if (!selectedRole) return;
    if (!fullName.trim()) {
      toast({ title: t("error"), description: selectedRole === "doctor" ? t("enter_doctor_name") : t("enter_patient_name"), variant: "destructive" });
      return;
    }
    if (!userPassword.trim()) {
      toast({ title: t("error"), description: t("enter_password"), variant: "destructive" });
      return;
    }

    if (selectedRole === "doctor" && !clinicPassword.trim()) {
      toast({ title: t("error"), description: t("enter_password"), variant: "destructive" });
      return;
    }

    if (selectedRole === "patient" && !patientLogin.trim()) {
      toast({ title: t("error"), description: t("enter_login"), variant: "destructive" });
      return;
    }

    setSaving(true);
    try {
      const session = await customRegister({
        role: selectedRole,
        full_name: fullName.trim(),
        password: userPassword.trim(),
        clinic_password: selectedRole === "doctor" ? clinicPassword.trim() : undefined,
        patient_login: selectedRole === "patient" ? patientLogin.trim() : undefined,
      });

      if (session.role === "doctor") {
        navigate("/doctor");
      } else {
        navigate("/patient");
      }
    } catch (err: unknown) {
      const error = err as Record<string, unknown>;
      const detail = (error?.message as string) || t("registration_error");
      toast({ title: t("error"), description: detail, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleLogin = async () => {
    if (!selectedRole) return;

    if (selectedRole === "doctor" && !fullName.trim()) {
      toast({ title: t("error"), description: t("enter_doctor_name"), variant: "destructive" });
      return;
    }

    if (selectedRole === "patient" && !patientLogin.trim()) {
      toast({ title: t("error"), description: t("enter_login"), variant: "destructive" });
      return;
    }

    if (!userPassword.trim()) {
      toast({ title: t("error"), description: t("enter_password"), variant: "destructive" });
      return;
    }

    setSaving(true);
    try {
      const session = await customLogin({
        role: selectedRole,
        full_name: selectedRole === "doctor" ? fullName.trim() : undefined,
        login: selectedRole === "patient" ? patientLogin.trim() : undefined,
        password: userPassword.trim(),
      });

      if (session.role === "doctor") {
        navigate("/doctor");
      } else {
        navigate("/patient");
      }
    } catch (err: unknown) {
      const error = err as Record<string, unknown>;
      const detail = (error?.message as string) || t("error");
      toast({ title: t("error"), description: detail, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (checkingSession) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex items-center justify-center">
        <Loader2 className="h-10 w-10 text-purple-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col">
      <AppHeader />

      <main className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-8">
        <div className="w-full max-w-md lg:max-w-lg">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white text-center mb-2">
            {mode === "register" ? (lang === "ru" ? "Регистрация" : "Registration") : t("role_selection_title")}
          </h2>
          <p className="text-gray-500 dark:text-gray-400 text-center mb-8">
            {lang === "ru" ? "Выберите вашу роль для продолжения" : "Select your role to continue"}
          </p>

          {/* Role Selection */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <button
              onClick={() => setSelectedRole("doctor")}
              className={`p-6 rounded-xl border-2 flex flex-col items-center gap-3 transition-all ${
                selectedRole === "doctor"
                  ? "border-purple-600 bg-purple-50 dark:bg-purple-900/30"
                  : "border-gray-200 dark:border-gray-700 hover:border-purple-300 dark:hover:border-purple-600"
              }`}
            >
              <Stethoscope className={`h-10 w-10 ${selectedRole === "doctor" ? "text-purple-600 dark:text-purple-400" : "text-gray-400"}`} />
              <span className={`font-medium ${selectedRole === "doctor" ? "text-purple-700 dark:text-purple-300" : "text-gray-600 dark:text-gray-400"}`}>
                {t("i_am_doctor")}
              </span>
            </button>

            <button
              onClick={() => setSelectedRole("patient")}
              className={`p-6 rounded-xl border-2 flex flex-col items-center gap-3 transition-all ${
                selectedRole === "patient"
                  ? "border-purple-600 bg-purple-50 dark:bg-purple-900/30"
                  : "border-gray-200 dark:border-gray-700 hover:border-purple-300 dark:hover:border-purple-600"
              }`}
            >
              <User className={`h-10 w-10 ${selectedRole === "patient" ? "text-purple-600 dark:text-purple-400" : "text-gray-400"}`} />
              <span className={`font-medium ${selectedRole === "patient" ? "text-purple-700 dark:text-purple-300" : "text-gray-600 dark:text-gray-400"}`}>
                {t("i_am_patient")}
              </span>
            </button>
          </div>

          {/* REGISTRATION MODE */}
          {mode === "register" && (
            <>
              {selectedRole === "doctor" && (
                <div className="space-y-4 animate-in fade-in duration-300">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("doctor_name")} *</label>
                    <Input
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder={t("doctor_name_placeholder")}
                      className="dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{lang === "ru" ? "Специальный пароль" : "Special password"} *</label>
                    <Input
                      type="password"
                      value={clinicPassword}
                      onChange={(e) => setClinicPassword(e.target.value)}
                      placeholder={lang === "ru" ? "Введите специальный пароль" : "Enter special password"}
                      className="dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("password_label")} *</label>
                    <Input
                      type="password"
                      value={userPassword}
                      onChange={(e) => setUserPassword(e.target.value)}
                      placeholder={t("enter_password")}
                      className="dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                    />
                  </div>
                  <Button
                    onClick={handleRegister}
                    disabled={saving}
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl mt-4"
                  >
                    {saving ? (
                      <><Loader2 className="mr-2 h-5 w-5 animate-spin" />{t("saving")}</>
                    ) : (
                      lang === "ru" ? "Зарегистрироваться" : "Register"
                    )}
                  </Button>
                </div>
              )}

              {selectedRole === "patient" && (
                <div className="space-y-4 animate-in fade-in duration-300">
                  <div className="bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700 rounded-xl p-4 text-center">
                    <p className="text-sm text-purple-700 dark:text-purple-300">
                      {t("patients_registered_by_doctors")}
                    </p>
                  </div>
                  <Button
                    onClick={() => switchMode("login")}
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl"
                  >
                    {lang === "ru" ? "Перейти к входу" : "Go to Login"}
                  </Button>
                </div>
              )}
            </>
          )}

          {/* LOGIN MODE */}
          {mode === "login" && (
            <>
              {selectedRole === "doctor" && (
                <div className="space-y-4 animate-in fade-in duration-300">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("doctor_name")} *</label>
                    <Input
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder={t("doctor_name_placeholder")}
                      className="dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("password_label")} *</label>
                    <Input
                      type="password"
                      value={userPassword}
                      onChange={(e) => setUserPassword(e.target.value)}
                      placeholder={t("enter_password")}
                      className="dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                    />
                  </div>
                  <Button
                    onClick={handleLogin}
                    disabled={saving}
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl mt-4"
                  >
                    {saving ? (
                      <><Loader2 className="mr-2 h-5 w-5 animate-spin" />{t("signing_in")}</>
                    ) : (
                      t("sign_in")
                    )}
                  </Button>
                </div>
              )}

              {selectedRole === "patient" && (
                <div className="space-y-4 animate-in fade-in duration-300">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("login_label")} *</label>
                    <Input
                      value={patientLogin}
                      onChange={(e) => setPatientLogin(e.target.value)}
                      placeholder={t("enter_login")}
                      className="dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("password_label")} *</label>
                    <Input
                      type="password"
                      value={userPassword}
                      onChange={(e) => setUserPassword(e.target.value)}
                      placeholder={t("enter_password")}
                      className="dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                    />
                  </div>
                  <Button
                    onClick={handleLogin}
                    disabled={saving}
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl mt-4"
                  >
                    {saving ? (
                      <><Loader2 className="mr-2 h-5 w-5 animate-spin" />{t("signing_in")}</>
                    ) : (
                      t("sign_in")
                    )}
                  </Button>
                </div>
              )}
            </>
          )}

          {/* Switch mode link */}
          <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
            {mode === "register" ? (
              <>
                {lang === "ru" ? "Уже зарегистрированы?" : "Already registered?"}{" "}
                <button onClick={() => switchMode("login")} className="text-purple-600 dark:text-purple-400 hover:underline font-medium">
                  {t("sign_in")}
                </button>
              </>
            ) : (
              <>
                {lang === "ru" ? "Нет аккаунта?" : "No account?"}{" "}
                <button onClick={() => switchMode("register")} className="text-purple-600 dark:text-purple-400 hover:underline font-medium">
                  {lang === "ru" ? "Зарегистрироваться" : "Register"}
                </button>
              </>
            )}
          </p>
        </div>
      </main>
    </div>
  );
}