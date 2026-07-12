import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Stethoscope, User, Loader2, ArrowLeft, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import {
  getSession,
  registerDoctor,
  loginDoctor,
  verifyDoctorEmail,
  requestPatientCode,
  verifyPatientCode,
} from "@/lib/auth";
import AppHeader from "@/components/AppHeader";
import { useLanguage } from "@/contexts/LanguageContext";

export default function RoleSelection() {
  const [mode, setMode] = useState<"register" | "login">("login");
  const [selectedRole, setSelectedRole] = useState<"doctor" | "patient" | null>(null);
  const [fullName, setFullName] = useState("");
  const [clinicPassword, setClinicPassword] = useState("");
  const [userPassword, setUserPassword] = useState("");
  const [email, setEmail] = useState("");

  // Email-code verification step (doctor first-time verify, or patient login).
  const [verifyStep, setVerifyStep] = useState<null | "doctor" | "patient">(null);
  const [verifyEmail, setVerifyEmail] = useState("");
  const [code, setCode] = useState("");

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
    setEmail("");
    setVerifyStep(null);
    setVerifyEmail("");
    setCode("");
  };

  const switchMode = (newMode: "register" | "login") => {
    setMode(newMode);
    resetForm();
  };

  const goToRole = (session: { role: string }) => {
    navigate(session.role === "doctor" ? "/doctor" : "/patient");
  };

  const errText = (err: unknown, fallback: string) => {
    const e = err as Record<string, unknown>;
    return (e?.message as string) || fallback;
  };

  // ---- Doctor register ----
  const handleDoctorRegister = async () => {
    if (!fullName.trim()) {
      toast({ title: t("error"), description: t("enter_doctor_name"), variant: "destructive" });
      return;
    }
    if (!email.trim() || !email.includes("@")) {
      toast({ title: t("error"), description: t("enter_email"), variant: "destructive" });
      return;
    }
    if (!clinicPassword.trim()) {
      toast({ title: t("error"), description: lang === "ru" ? "Введите специальный пароль" : "Enter special password", variant: "destructive" });
      return;
    }
    if (!userPassword.trim()) {
      toast({ title: t("error"), description: t("enter_password"), variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      const res = await registerDoctor({
        full_name: fullName.trim(),
        email: email.trim(),
        password: userPassword.trim(),
        clinic_password: clinicPassword.trim(),
      });
      if (res.needsVerification) {
        setVerifyEmail(res.email || email.trim());
        setVerifyStep("doctor");
      } else if (res.session) {
        goToRole(res.session);
      }
    } catch (err) {
      toast({ title: t("error"), description: errText(err, t("registration_error")), variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  // ---- Doctor login ----
  const handleDoctorLogin = async () => {
    if (!email.trim() || !email.includes("@")) {
      toast({ title: t("error"), description: t("enter_email"), variant: "destructive" });
      return;
    }
    if (!userPassword.trim()) {
      toast({ title: t("error"), description: t("enter_password"), variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      const res = await loginDoctor({ email: email.trim(), password: userPassword.trim() });
      if (res.needsVerification) {
        setVerifyEmail(res.email || email.trim());
        setVerifyStep("doctor");
      } else if (res.session) {
        goToRole(res.session);
      }
    } catch (err) {
      toast({ title: t("error"), description: errText(err, t("error")), variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  // ---- Patient login: request code ----
  const handlePatientRequestCode = async () => {
    if (!email.trim() || !email.includes("@")) {
      toast({ title: t("error"), description: t("enter_email"), variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      await requestPatientCode(email.trim());
      setVerifyEmail(email.trim());
      setVerifyStep("patient");
    } catch (err) {
      toast({ title: t("error"), description: errText(err, t("error")), variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  // ---- Verify code (doctor or patient) ----
  const handleVerifyCode = async () => {
    if (!code.trim()) {
      toast({ title: t("error"), description: t("enter_code"), variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      const session =
        verifyStep === "doctor"
          ? await verifyDoctorEmail({ email: verifyEmail, code: code.trim() })
          : await verifyPatientCode({ email: verifyEmail, code: code.trim() });
      goToRole(session);
    } catch (err) {
      toast({ title: t("error"), description: errText(err, t("error")), variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handleResendCode = async () => {
    setSaving(true);
    try {
      if (verifyStep === "patient") {
        await requestPatientCode(verifyEmail);
      } else {
        // Re-issues a code for an unverified doctor (password is still in state).
        await loginDoctor({ email: verifyEmail, password: userPassword.trim() });
      }
      toast({ title: t("code_resent") });
    } catch (err) {
      toast({ title: t("error"), description: errText(err, t("error")), variant: "destructive" });
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

  const inputClass = "dark:bg-gray-800 dark:border-gray-700 dark:text-white";

  // ---- Code entry view ----
  if (verifyStep) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col">
        <AppHeader />
        <main className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-8">
          <div className="w-full max-w-md">
            <button
              onClick={() => { setVerifyStep(null); setCode(""); }}
              className="text-purple-600 dark:text-purple-400 text-sm mb-6 flex items-center gap-1 hover:underline"
            >
              <ArrowLeft className="h-4 w-4" />
              {t("back")}
            </button>

            <div className="flex justify-center mb-4">
              <div className="w-14 h-14 rounded-2xl bg-purple-100 dark:bg-purple-900/40 flex items-center justify-center">
                <Mail className="h-7 w-7 text-purple-600 dark:text-purple-400" />
              </div>
            </div>
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white text-center mb-2">
              {t("verification_code")}
            </h2>
            <p className="text-gray-500 dark:text-gray-400 text-center mb-6">
              {t("code_sent_to")} <span className="font-medium text-gray-700 dark:text-gray-200">{verifyEmail}</span>
            </p>

            <Input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoFocus
              placeholder="000000"
              className={`${inputClass} text-center text-2xl tracking-[0.5em] font-mono py-6`}
              onKeyDown={(e) => { if (e.key === "Enter") handleVerifyCode(); }}
            />

            <Button
              onClick={handleVerifyCode}
              disabled={saving || code.length < 4}
              className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl mt-4"
            >
              {saving ? <><Loader2 className="mr-2 h-5 w-5 animate-spin" />{t("verifying")}</> : t("confirm")}
            </Button>

            <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
              <button onClick={handleResendCode} disabled={saving} className="text-purple-600 dark:text-purple-400 hover:underline font-medium disabled:opacity-50">
                {t("resend_code")}
              </button>
            </p>
          </div>
        </main>
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
          {mode === "register" && selectedRole === "doctor" && (
            <div className="space-y-4 animate-in fade-in duration-300">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("doctor_name")} *</label>
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder={t("doctor_name_placeholder")} className={inputClass} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("email_label")} *</label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("email_placeholder")} className={inputClass} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{lang === "ru" ? "Специальный пароль" : "Special password"} *</label>
                <Input type="password" value={clinicPassword} onChange={(e) => setClinicPassword(e.target.value)} placeholder={lang === "ru" ? "Введите специальный пароль" : "Enter special password"} className={inputClass} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("password_label")} *</label>
                <Input type="password" value={userPassword} onChange={(e) => setUserPassword(e.target.value)} placeholder={t("enter_password")} className={inputClass} />
              </div>
              <Button onClick={handleDoctorRegister} disabled={saving} className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl mt-4">
                {saving ? <><Loader2 className="mr-2 h-5 w-5 animate-spin" />{t("saving")}</> : (lang === "ru" ? "Зарегистрироваться" : "Register")}
              </Button>
            </div>
          )}

          {mode === "register" && selectedRole === "patient" && (
            <div className="space-y-4 animate-in fade-in duration-300">
              <div className="bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700 rounded-xl p-4 text-center">
                <p className="text-sm text-purple-700 dark:text-purple-300">{t("patients_registered_by_doctors")}</p>
              </div>
              <Button onClick={() => switchMode("login")} className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl">
                {lang === "ru" ? "Перейти к входу" : "Go to Login"}
              </Button>
            </div>
          )}

          {/* LOGIN MODE */}
          {mode === "login" && selectedRole === "doctor" && (
            <div className="space-y-4 animate-in fade-in duration-300">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("email_label")} *</label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("email_placeholder")} className={inputClass} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("password_label")} *</label>
                <Input type="password" value={userPassword} onChange={(e) => setUserPassword(e.target.value)} placeholder={t("enter_password")} className={inputClass} onKeyDown={(e) => { if (e.key === "Enter") handleDoctorLogin(); }} />
              </div>
              <Button onClick={handleDoctorLogin} disabled={saving} className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl mt-4">
                {saving ? <><Loader2 className="mr-2 h-5 w-5 animate-spin" />{t("signing_in")}</> : t("sign_in")}
              </Button>
            </div>
          )}

          {mode === "login" && selectedRole === "patient" && (
            <div className="space-y-4 animate-in fade-in duration-300">
              <div className="bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700 rounded-xl p-3 text-center">
                <p className="text-xs text-purple-700 dark:text-purple-300">{t("patient_login_email_hint")}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("email_label")} *</label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("email_placeholder")} className={inputClass} onKeyDown={(e) => { if (e.key === "Enter") handlePatientRequestCode(); }} />
              </div>
              <Button onClick={handlePatientRequestCode} disabled={saving} className="w-full bg-purple-600 hover:bg-purple-700 text-white py-5 text-lg rounded-xl mt-4">
                {saving ? <><Loader2 className="mr-2 h-5 w-5 animate-spin" />{t("sending_code")}</> : t("get_code")}
              </Button>
            </div>
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
