import { useState } from "react";
import { Button } from "@/components/ui/button";
import { client } from "@/lib/auth";
import { useToast } from "@/hooks/use-toast";
import { useLanguage } from "@/contexts/LanguageContext";

export default function ShareReportButton({ reportId, existingToken }: { reportId?: number; existingToken?: string }) {
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();
  const { lang } = useLanguage();
  if (!reportId) return null;
  const share = async () => {
    setBusy(true);
    try {
      let token = existingToken;
      if (!token) {
        const res = await client.apiCall.invoke({ url: `/api/v1/reports/${reportId}/share`, method: "POST" });
        token = res.data.token;
      }
      const url = `${window.location.origin}/report/${reportId}#token=${encodeURIComponent(token!)}`;
      await navigator.clipboard.writeText(url);
      toast({ title: lang === "ru" ? "Защищённая ссылка скопирована" : "Secure link copied", description: lang === "ru" ? "Доступ по ссылке действует до 7 дней. Передавайте её только получателю отчёта." : "The link expires within 7 days. Share it only with the intended recipient." });
    } catch {
      toast({ title: lang === "ru" ? "Не удалось скопировать ссылку. Войдите в аккаунт и повторите." : "Could not copy the link. Sign in and try again.", variant: "destructive" });
    } finally { setBusy(false); }
  };
  return <Button variant="outline" disabled={busy} onClick={share}>{lang === "ru" ? "Поделиться защищённой ссылкой" : "Share secure link"}</Button>;
}
