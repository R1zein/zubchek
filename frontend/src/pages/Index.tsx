import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, Upload, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { getSession, client } from "@/lib/auth";
import AppHeader from "@/components/AppHeader";

export default function Index() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  const [user, setUser] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = () => {
    try {
      const session = getSession();
      if (session) {
        setUser(session);
        if (session.role === "doctor") {
          navigate("/doctor");
          return;
        } else if (session.role === "patient") {
          navigate("/patient");
          return;
        }
      }
    } catch {
      // Not authenticated, show landing page
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogin = () => {
    navigate("/role-selection");
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const analyzeImage = async (imageDataUri: string) => {
    setIsAnalyzing(true);
    try {
      const session = getSession();
      const url = session
        ? `/api/v1/analysis/analyze?current_user_id=${encodeURIComponent(session.user_id)}`
        : "/api/v1/analysis/analyze";
      const response = await client.apiCall.invoke({
        url,
        method: "POST",
        data: { image: imageDataUri },
        options: { timeout: 600_000 },
      });

      const result = response?.data ?? response;

      if (result.error === "no_teeth") {
        toast({
          title: "Зубы не обнаружены",
          description: result.message || "На фото не обнаружены зубы.",
          variant: "destructive",
        });
        setIsAnalyzing(false);
        return;
      }

      if (result.error === "no_dye_detected") {
        toast({
          title: "Краситель не обнаружен",
          description: result.message || "Краситель не обнаружен.",
          variant: "destructive",
        });
        setIsAnalyzing(false);
        return;
      }

      if (!result.has_teeth && result.error) {
        toast({
          title: "Ошибка анализа",
          description: result.message || "Не удалось проанализировать фото.",
          variant: "destructive",
        });
        setIsAnalyzing(false);
        return;
      }

      navigate("/results", {
        state: { analysisResult: result, imageDataUri },
      });
    } catch (err: any) {
      const detail =
        err?.data?.detail ||
        err?.response?.data?.detail ||
        err?.data?.message ||
        err?.message ||
        "Ошибка анализа. Попробуйте ещё раз.";
      toast({ title: "Ошибка", description: detail, variant: "destructive" });
    } finally {
      setIsAnalyzing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast({ title: "Ошибка", description: "Пожалуйста, выберите изображение", variant: "destructive" });
      return;
    }

    const reader = new FileReader();
    reader.onload = async () => {
      const imageDataUri = reader.result as string;
      await analyzeImage(imageDataUri);
    };
    reader.readAsDataURL(file);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <Loader2 className="h-10 w-10 text-purple-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      {/* Header */}
      <AppHeader
        showLogin={!user}
        onLogin={handleLogin}
      />

      {/* Main Content */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        {isAnalyzing ? (
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="h-12 w-12 sm:h-16 sm:w-16 text-purple-600 animate-spin" />
            <p className="text-base sm:text-lg text-gray-600">Анализируем фото...</p>
            <p className="text-xs sm:text-sm text-gray-400">
              Это может занять несколько секунд
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4 sm:gap-6 w-full max-w-sm sm:max-w-md lg:max-w-lg text-center">
            <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-full bg-purple-100 flex items-center justify-center">
              <Camera className="h-10 w-10 sm:h-12 sm:w-12 text-purple-600" />
            </div>

            <div>
              <h2 className="text-xl sm:text-2xl font-semibold text-gray-800 mb-2">
                Анализ гигиены полости рта
              </h2>
              <p className="text-sm sm:text-base text-gray-500">
                Загрузите фото зубов, окрашенных индикатором налёта, для оценки
                по методике PHP
              </p>
            </div>

            <Button
              onClick={handleFileSelect}
              size="lg"
              className="bg-purple-600 hover:bg-purple-700 text-white px-6 sm:px-8 py-5 sm:py-6 text-base sm:text-lg rounded-xl shadow-lg w-full sm:w-auto"
            >
              <Upload className="mr-2 h-5 w-5" />
              Загрузить фото
            </Button>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />

            {!user && (
              <p className="text-xs text-gray-400 mt-2">
                <button onClick={handleLogin} className="text-purple-600 hover:underline">
                  Войдите
                </button>
                , чтобы сохранять отчёты в личном кабинете
              </p>
            )}

            <div className="mt-4 sm:mt-8 p-3 sm:p-4 bg-gray-50 rounded-xl text-left w-full">
              <h3 className="font-medium text-gray-700 mb-2 text-sm sm:text-base">
                Как это работает:
              </h3>
              <ol className="text-xs sm:text-sm text-gray-500 space-y-1 list-decimal list-inside">
                <li>Нанесите индикатор налёта на зубы</li>
                <li>Сделайте фото зубов</li>
                <li>Загрузите фото для анализа</li>
                <li>Получите результат оценки гигиены</li>
              </ol>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}