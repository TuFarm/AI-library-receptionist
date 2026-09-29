import { Navigate, Route, Routes } from "react-router-dom";
import AdminLayout from "./layouts/AdminLayout";
import KioskLayout from "./layouts/KioskLayout";
import LandingPage from "./pages/LandingPage";
import KioskApp from "./pages/kiosk/KioskApp";
import KioskDeviceGate from "./components/kiosk/KioskDeviceGate";
import StaffAccountsPage from "./pages/admin/StaffAccountsPage";
import DevicesPage from "./pages/admin/DevicesPage";
import FeatureStatusPage from "./pages/admin/FeatureStatusPage";
import AdminDashboardPage from "./pages/admin/AdminDashboardPage";
import KnowledgePage from "./pages/admin/KnowledgePage";
import ConversationLogsPage from "./pages/admin/ConversationLogsPage";
import UserManagementPage from "./pages/admin/UserManagementPage";
import SurveyManagementPage from "./pages/admin/SurveyManagementPage";
import ReportsPage from "./pages/admin/ReportsPage";
import { NotFoundPage } from "./pages/Pages";

export default function App(){return <Routes>
  <Route path="/" element={<LandingPage/>}/>
  <Route path="/kiosk" element={<KioskLayout/>}><Route index element={<Navigate to="fullscreen" replace/>}/><Route path="fullscreen" element={<KioskDeviceGate><KioskApp/></KioskDeviceGate>}/></Route>
  <Route path="/admin" element={<AdminLayout/>}><Route index element={<Navigate to="dashboard" replace/>}/><Route path="dashboard" element={<AdminDashboardPage/>}/><Route path="knowledge" element={<KnowledgePage/>}/><Route path="conversations" element={<ConversationLogsPage/>}/><Route path="users" element={<UserManagementPage/>}/><Route path="surveys" element={<SurveyManagementPage/>}/><Route path="reports" element={<ReportsPage/>}/><Route path="status" element={<FeatureStatusPage/>}/><Route path="staff" element={<StaffAccountsPage/>}/><Route path="devices" element={<DevicesPage/>}/></Route>
  <Route path="*" element={<NotFoundPage/>}/>
</Routes>}
