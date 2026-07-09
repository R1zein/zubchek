import { Toaster as SonnerToaster } from '@/components/ui/sonner';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { LanguageProvider } from '@/contexts/LanguageContext';
import Landing from './pages/Landing';
import Results from './pages/Results';
import SharedReport from './pages/SharedReport';
import AuthCallback from './pages/AuthCallback';
import AuthError from './pages/AuthError';
import RoleSelection from './pages/RoleSelection';
import DoctorDashboard from './pages/DoctorDashboard';
import PatientDashboard from './pages/PatientDashboard';

const queryClient = new QueryClient();

const AppRoutes = () => (
  <Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/login" element={<RoleSelection />} />
    <Route path="/results" element={<Results />} />
    <Route path="/report/:reportId" element={<SharedReport />} />
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/auth/error" element={<AuthError />} />
    <Route path="/role-selection" element={<RoleSelection />} />
    <Route path="/doctor" element={<DoctorDashboard />} />
    <Route path="/patient" element={<PatientDashboard />} />
  </Routes>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <LanguageProvider>
        <TooltipProvider>
          <SonnerToaster />
          <Toaster />
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </TooltipProvider>
      </LanguageProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
export { AppRoutes };