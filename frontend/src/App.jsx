import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './auth/AuthContext';
import Layout from './components/Layout';
import { Spinner } from './components/ui';
import Login from './pages/hr/Login';

const Dashboard = lazy(() => import('./pages/hr/Dashboard'));
const Jobs = lazy(() => import('./pages/hr/Jobs'));
const JobDetail = lazy(() => import('./pages/hr/JobDetail'));
const Candidates = lazy(() => import('./pages/hr/Candidates'));
const CandidateDetail = lazy(() => import('./pages/hr/CandidateDetail'));
const Interviews = lazy(() => import('./pages/hr/Interviews'));
const InterviewDetail = lazy(() => import('./pages/hr/InterviewDetail'));
const Reports = lazy(() => import('./pages/hr/Reports'));
const ReportDetail = lazy(() => import('./pages/hr/ReportDetail'));
const Settings = lazy(() => import('./pages/hr/Settings'));
const Users = lazy(() => import('./pages/hr/Users'));
const AuditLog = lazy(() => import('./pages/hr/AuditLog'));
const InterviewEntry = lazy(() => import('./pages/candidate/InterviewEntry'));

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        {/* Candidate experience: no HR chrome, authenticated only by the invitation link */}
        <Route path="/interview/:token" element={<InterviewEntry />} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Dashboard />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="candidates" element={<Candidates />} />
          <Route path="candidates/:id" element={<CandidateDetail />} />
          <Route path="interviews" element={<Interviews />} />
          <Route path="interviews/:id" element={<InterviewDetail />} />
          <Route path="reports" element={<Reports />} />
          <Route path="reports/:id" element={<ReportDetail />} />
          <Route path="settings" element={<Settings />} />
          <Route path="users" element={<RequireAuth admin><Users /></RequireAuth>} />
          <Route path="audit" element={<RequireAuth admin><AuditLog /></RequireAuth>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
