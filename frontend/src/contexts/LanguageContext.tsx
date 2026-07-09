import { createContext, useContext, useState, ReactNode } from "react";
import { Lang, t, TranslationKey } from "@/lib/i18n";

interface LanguageContextType {
  lang: Lang;
  toggleLang: () => void;
  t: (key: TranslationKey) => string;
}

const LanguageContext = createContext<LanguageContextType>({
  lang: "ru",
  toggleLang: () => {},
  t: (key) => key,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const saved = localStorage.getItem("zubchek-lang");
    return (saved === "ru" || saved === "en") ? saved : "ru";
  });

  const toggleLang = () => {
    setLang((prev) => {
      const next = prev === "ru" ? "en" : "ru";
      localStorage.setItem("zubchek-lang", next);
      return next;
    });
  };

  const translate = (key: TranslationKey) => t(key, lang);

  return (
    <LanguageContext.Provider value={{ lang, toggleLang, t: translate }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}