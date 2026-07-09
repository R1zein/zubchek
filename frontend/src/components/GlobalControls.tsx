import { Moon, Sun, Globe } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { useLanguage } from "@/contexts/LanguageContext";

export default function GlobalControls() {
  const { theme, toggleTheme } = useTheme();
  const { lang, toggleLang } = useLanguage();

  return (
    <div className="flex items-center" style={{ gap: 'clamp(0.125rem, 1vw, 0.5rem)' }}>
      <button
        onClick={toggleTheme}
        className="rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-700 transition-colors"
        style={{ padding: 'clamp(0.25rem, 1.5vw, 0.5rem)' }}
        aria-label="Toggle theme"
      >
        {theme === "light" ? (
          <Moon style={{ width: 'clamp(1.25rem, 3vw + 0.5rem, 2rem)', height: 'clamp(1.25rem, 3vw + 0.5rem, 2rem)' }} />
        ) : (
          <Sun style={{ width: 'clamp(1.25rem, 3vw + 0.5rem, 2rem)', height: 'clamp(1.25rem, 3vw + 0.5rem, 2rem)' }} />
        )}
      </button>
      <button
        onClick={toggleLang}
        className="rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-700 transition-colors flex items-center"
        style={{ padding: 'clamp(0.25rem, 1.5vw, 0.5rem)', gap: 'clamp(0.125rem, 0.5vw, 0.25rem)' }}
        aria-label="Toggle language"
      >
        <Globe style={{ width: 'clamp(1.25rem, 3vw + 0.5rem, 2rem)', height: 'clamp(1.25rem, 3vw + 0.5rem, 2rem)' }} />
        <span className="font-medium uppercase" style={{ fontSize: 'clamp(0.625rem, 1.5vw + 0.25rem, 0.875rem)' }}>{lang}</span>
      </button>
    </div>
  );
}