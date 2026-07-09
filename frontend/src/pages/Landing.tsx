import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getSession } from "@/lib/auth";
import { Activity, BarChart3, FileText, Users, ArrowRight, Sparkles, Shield, Zap } from "lucide-react";
import Logo from "@/components/Logo";

export default function Landing() {
  const navigate = useNavigate();

  useEffect(() => {
    const session = getSession();
    if (session) {
      if (session.role === "doctor") {
        navigate("/doctor", { replace: true });
      } else {
        navigate("/patient", { replace: true });
      }
    }
  }, [navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950 to-slate-950 text-white overflow-hidden">
      {/* Animated background elements */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-20 left-10 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-20 right-10 w-96 h-96 bg-violet-500/10 rounded-full blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-purple-600/5 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-6 sm:px-10 lg:px-16 py-5">
        <Logo size="sm" />
        <button
          onClick={() => navigate("/login")}
          className="flex items-center gap-2 px-5 py-2.5 rounded-full border border-purple-400/30 text-purple-200 hover:bg-purple-500/20 hover:border-purple-400/60 transition-all duration-300 text-sm font-medium backdrop-blur-sm"
        >
          Войти
          <ArrowRight className="h-4 w-4" />
        </button>
      </header>

      {/* Hero Section */}
      <section className="relative z-10 flex flex-col items-center text-center px-6 pt-12 pb-12 sm:pt-16 sm:pb-16">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-purple-500/10 border border-purple-500/20 mb-8 backdrop-blur-sm">
          <Sparkles className="h-4 w-4 text-purple-400" />
          <span className="text-sm text-purple-300">AI-анализ гигиены полости рта</span>
        </div>
        
        <h1 className="text-4xl sm:text-5xl lg:text-7xl font-bold leading-tight max-w-4xl">
          <span className="bg-gradient-to-r from-white via-purple-100 to-purple-300 bg-clip-text text-transparent">
            Объективная оценка
          </span>
          <br />
          <span className="bg-gradient-to-r from-purple-300 via-violet-400 to-purple-500 bg-clip-text text-transparent">
            гигиены зубов
          </span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-gray-400 max-w-2xl leading-relaxed">
          Загрузите фото зубов, окрашенных индикатором налёта, и получите детальный анализ 
          по каждому зубу за секунды
        </p>

        <div className="mt-10 flex flex-col sm:flex-row gap-4">
          <button
            onClick={() => navigate("/login")}
            className="group px-8 py-4 rounded-xl bg-gradient-to-r from-purple-600 to-violet-600 hover:from-purple-500 hover:to-violet-500 text-white font-semibold text-lg shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 transition-all duration-300 flex items-center gap-2"
          >
            Начать работу
            <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
          </button>
        </div>
      </section>

      {/* Z-Index Section */}
      <section className="relative z-10 px-6 sm:px-10 lg:px-16 py-12">
        <div className="max-w-6xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 mb-6">
                <Activity className="h-4 w-4 text-violet-400" />
                <span className="text-sm text-violet-300">Уникальная методика</span>
              </div>
              <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold mb-6">
                <span className="bg-gradient-to-r from-white to-purple-200 bg-clip-text text-transparent">
                  Индекс Z
                </span>
              </h2>
              <p className="text-gray-400 text-lg leading-relaxed mb-8">
                Индекс Z — это комплексная оценка уровня гигиены полости рта. 
                AI анализирует окрашенные зубы и определяет процент налёта на каждом зубе, 
                учитывая возраст и свежесть отложений по цвету красителя.
              </p>
              <div className="space-y-4">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                    <span className="text-purple-400 font-bold text-sm">1</span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-white">Загрузите фото</h4>
                    <p className="text-gray-500 text-sm">Сфотографируйте зубы после нанесения индикатора налёта</p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-violet-500/20 flex items-center justify-center">
                    <span className="text-violet-400 font-bold text-sm">2</span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-white">AI-анализ</h4>
                    <p className="text-gray-500 text-sm">Нейросеть определяет площадь и тип налёта на каждом зубе</p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-fuchsia-500/20 flex items-center justify-center">
                    <span className="text-fuchsia-400 font-bold text-sm">3</span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-white">Детальный отчёт</h4>
                    <p className="text-gray-500 text-sm">Получите индекс по каждому зубу и рекомендации</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Visual card */}
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-r from-purple-600/20 to-violet-600/20 rounded-3xl blur-xl" />
              <div className="relative bg-gradient-to-br from-slate-900/80 to-purple-950/80 border border-purple-500/20 rounded-3xl p-8 backdrop-blur-xl">
                <div className="text-center mb-6">
                  <p className="text-sm text-gray-400 mb-2">Индекс налёта</p>
                  <div className="text-6xl font-bold bg-gradient-to-r from-green-400 to-emerald-400 bg-clip-text text-transparent">
                    23%
                  </div>
                  <p className="text-sm text-gray-500 mt-1">Чистота: 77%</p>
                  <div className="mt-3 inline-block px-4 py-1.5 rounded-full bg-green-500/20 border border-green-500/30">
                    <span className="text-green-400 text-sm font-medium">Низкий индекс налёта</span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3 mt-6">
                  {[
                    { tooth: "1.1", pct: "15%" },
                    { tooth: "1.2", pct: "28%" },
                    { tooth: "1.3", pct: "32%" },
                    { tooth: "2.1", pct: "12%" },
                    { tooth: "2.2", pct: "20%" },
                    { tooth: "2.3", pct: "25%" },
                  ].map((item) => (
                    <div key={item.tooth} className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
                      <p className="text-xs text-gray-500">{item.tooth}</p>
                      <p className="text-lg font-bold text-purple-300">{item.pct}</p>
                      <p className="text-[10px] text-gray-600">налёт</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="relative z-10 px-6 sm:px-10 lg:px-16 py-12">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold bg-gradient-to-r from-white to-purple-200 bg-clip-text text-transparent">
              Возможности платформы
            </h2>
            <p className="mt-4 text-gray-400 max-w-xl mx-auto">
              Всё необходимое для профессиональной оценки гигиены полости рта
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              {
                icon: Activity,
                title: "AI-анализ гигиены",
                desc: "Автоматическое определение индексов гигиены по фото с индикатором налёта",
                gradient: "from-purple-500 to-violet-500",
              },
              {
                icon: BarChart3,
                title: "Детализация по зубам",
                desc: "Процент налёта для каждого из 12 фронтальных зубов отдельно",
                gradient: "from-violet-500 to-fuchsia-500",
              },
              {
                icon: FileText,
                title: "Отчёты и история",
                desc: "Сохранение результатов анализа и отслеживание динамики гигиены",
                gradient: "from-fuchsia-500 to-pink-500",
              },
              {
                icon: Users,
                title: "Управление пациентами",
                desc: "Личный кабинет врача с базой пациентов и их отчётами",
                gradient: "from-pink-500 to-rose-500",
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="group relative bg-slate-900/50 border border-slate-800 hover:border-purple-500/30 rounded-2xl p-6 transition-all duration-300 hover:shadow-lg hover:shadow-purple-500/5"
              >
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${feature.gradient} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300`}>
                  <feature.icon className="h-6 w-6 text-white" />
                </div>
                <h3 className="font-semibold text-white text-lg mb-2">{feature.title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* For whom section */}
      <section className="relative z-10 px-6 sm:px-10 lg:px-16 py-12">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold bg-gradient-to-r from-white to-purple-200 bg-clip-text text-transparent">
              Для кого
            </h2>
          </div>

          <div className="grid sm:grid-cols-2 gap-8 max-w-3xl mx-auto">
            <div className="relative overflow-hidden bg-gradient-to-br from-slate-900/80 to-purple-950/40 border border-purple-500/20 rounded-2xl p-8 hover:border-purple-500/40 transition-all duration-300">
              <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
              <Shield className="h-10 w-10 text-purple-400 mb-4" />
              <h3 className="text-xl font-bold text-white mb-3">Стоматологи</h3>
              <p className="text-gray-400 leading-relaxed">
                Объективный инструмент для оценки гигиены пациентов. 
                Ведите базу пациентов, отслеживайте динамику и демонстрируйте результаты.
              </p>
            </div>

            <div className="relative overflow-hidden bg-gradient-to-br from-slate-900/80 to-violet-950/40 border border-violet-500/20 rounded-2xl p-8 hover:border-violet-500/40 transition-all duration-300">
              <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/10 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
              <Zap className="h-10 w-10 text-violet-400 mb-4" />
              <h3 className="text-xl font-bold text-white mb-3">Пациенты</h3>
              <p className="text-gray-400 leading-relaxed">
                Следите за состоянием гигиены полости рта. 
                Получайте понятные отчёты и видите прогресс после каждого визита.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Back to top */}
      <section className="relative z-10 px-6 sm:px-10 lg:px-16 py-6 flex justify-center">
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="group px-8 py-4 rounded-xl bg-gradient-to-r from-purple-600 to-violet-600 hover:from-purple-500 hover:to-violet-500 text-white font-semibold text-lg shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 transition-all duration-300 inline-flex items-center gap-2"
        >
          К началу
          <ArrowRight className="h-5 w-5 group-hover:-translate-y-1 transition-transform rotate-[-90deg]" />
        </button>
      </section>



    </div>
  );
}