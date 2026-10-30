import "@fontsource-variable/inter";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ApiProvider } from "./app/ApiProvider";
import { AuthProvider } from "./app/AuthProvider";
import { ROUTER_FUTURE } from "./app/nav";
import { ToastProvider } from "./app/ToastProvider";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter future={ROUTER_FUTURE}>
      <ToastProvider>
        <ApiProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ApiProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
