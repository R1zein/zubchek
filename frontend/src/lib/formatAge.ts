/**
 * Вычисляет возраст на основе даты рождения и возвращает форматированную строку.
 * Возраст вычисляется динамически (не хранится отдельно).
 */
export function formatAge(birthDate: string | null, lang: string): string {
  if (!birthDate) return "";
  const birth = new Date(birthDate);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) {
    age--;
  }
  if (lang === "en") return `${age} y.o.`;
  const lastTwo = age % 100;
  const lastOne = age % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${age} лет`;
  if (lastOne === 1) return `${age} год`;
  if (lastOne >= 2 && lastOne <= 4) return `${age} года`;
  return `${age} лет`;
}

/**
 * Вычисляет возраст в годах (числовое значение) на основе даты рождения.
 * Полезно для будущей логики (фильтрация, рекомендации по возрасту и т.д.)
 */
export function calculateAge(birthDate: string | null): number | null {
  if (!birthDate) return null;
  const birth = new Date(birthDate);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) {
    age--;
  }
  return age;
}