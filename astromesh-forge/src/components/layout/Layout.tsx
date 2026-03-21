import { Outlet } from "react-router-dom";
import { Header } from "./Header";
import { ToastContainer } from "../ui/Toast";

export function Layout() {
  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-100">
      <Header />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
      <ToastContainer />
    </div>
  );
}
