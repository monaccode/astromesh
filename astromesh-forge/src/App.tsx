import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { Dashboard } from "./components/dashboard/Dashboard";
import { WizardShell } from "./components/wizard/WizardShell";
import { CanvasEditor } from "./components/canvas/CanvasEditor";
import { TemplateGallery } from "./components/templates/TemplateGallery";
import { ConsoleShell } from "./components/console/ConsoleShell";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/wizard" element={<WizardShell />} />
          <Route path="/wizard/:name" element={<WizardShell />} />
          <Route path="/canvas" element={<CanvasEditor />} />
          <Route path="/canvas/:name" element={<CanvasEditor />} />
          <Route path="/templates" element={<TemplateGallery />} />
          <Route path="/console" element={<ConsoleShell />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
