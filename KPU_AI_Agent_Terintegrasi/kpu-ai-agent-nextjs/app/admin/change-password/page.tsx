import AdminAuthForms from '@/components/AdminAuthForms';
import AdminShell from '@/components/AdminShell';
export default function AdminChangePasswordPage() {
  return <AdminShell><div className="admin-content"><AdminAuthForms kind="change" /></div></AdminShell>;
}
