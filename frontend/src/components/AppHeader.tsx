import { ArrowLeft, LogOut, LogIn } from "lucide-react";
import { useNavigate } from "react-router-dom";
import Logo from "@/components/Logo";
import GlobalControls from "@/components/GlobalControls";
import { useLanguage } from "@/contexts/LanguageContext";

interface AppHeaderProps {
  showBack?: boolean;
  backTo?: string | number;
  showLogout?: boolean;
  onLogout?: () => void;
  showLogin?: boolean;
  onLogin?: () => void;
  userName?: string;
  badge?: { label: string; color: string };
  extraInfo?: string;
}

export default function AppHeader({
  showBack = false,
  backTo,
  showLogout = false,
  onLogout,
  showLogin = false,
  onLogin,
  userName,
  badge,
  extraInfo,
}: AppHeaderProps) {
  const navigate = useNavigate();
  const { lang } = useLanguage();

  const handleBack = () => {
    if (typeof backTo === "number") {
      navigate(backTo as number);
    } else if (typeof backTo === "string") {
      navigate(backTo);
    } else {
      navigate(-1);
    }
  };

  return (
    <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 sm:px-6 lg:px-8 py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {showBack && (
            <button
              onClick={handleBack}
              className="flex items-center gap-1 text-gray-500 hover:text-purple-600 dark:text-gray-400 dark:hover:text-purple-400 transition-colors mr-1"
            >
              <ArrowLeft className="h-4 w-4 sm:h-5 sm:w-5" />
              <span className="text-sm hidden sm:inline">{lang === "ru" ? "Назад" : "Back"}</span>
            </button>
          )}
          <Logo size="sm" />
          {badge && (
            <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${badge.color}`}>
              {badge.label}
            </span>
          )}
          {extraInfo && (
            <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">{extraInfo}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <GlobalControls />
          {userName && (
            <span className="text-sm text-gray-600 dark:text-gray-300 font-medium hidden sm:inline">
              {userName}
            </span>
          )}
          {showLogout && onLogout && (
            <button
              onClick={onLogout}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <LogOut className="h-4 w-4" />
            </button>
          )}
          {showLogin && onLogin && (
            <button
              onClick={onLogin}
              className="flex items-center gap-1 text-sm border border-purple-200 dark:border-purple-700 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30 px-3 py-1.5 rounded-lg transition-colors"
            >
              <LogIn className="h-4 w-4" />
              <span>{lang === "ru" ? "Войти" : "Login"}</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}