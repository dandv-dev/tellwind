import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en";
import ru from "./ru";
import uk from "./uk";

export const LANGS = [
  { code: "en", label: "English", short: "EN" },
  { code: "ru", label: "Русский", short: "RU" },
  { code: "uk", label: "Українська", short: "UA" },
] as const;
export type Lang = (typeof LANGS)[number]["code"];

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("tw-lang");
    if (saved === "en" || saved === "ru" || saved === "uk") return saved;
  } catch {
    /* storage blocked */
  }
  const nav = (typeof navigator !== "undefined" ? navigator.language : "en").slice(0, 2);
  return nav === "ru" ? "ru" : nav === "uk" ? "uk" : "en";
}

export function setupI18n(fixed?: Lang) {
  if (i18n.isInitialized) return i18n;
  i18n.use(initReactI18next).init({
    resources: { en: { translation: en }, ru: { translation: ru }, uk: { translation: uk } },
    lng: fixed ?? initialLang(),
    fallbackLng: "en",
    interpolation: { escapeValue: false },
  });
  document.documentElement.lang = i18n.language;
  i18n.on("languageChanged", (l) => {
    document.documentElement.lang = l;
    if (fixed) return;
    try {
      localStorage.setItem("tw-lang", l);
    } catch {
      /* ignore */
    }
  });
  return i18n;
}

export default i18n;
