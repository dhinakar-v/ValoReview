import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import "./app.css";
import { MatchListPage } from "./pages/MatchList";
import { ViewerPage } from "./pages/Viewer";
import { AppFrame } from "./views/AppFrame";

// A local server reading files off a disk: nothing here goes stale on its own,
// so refetching on window focus is pure noise.
const client = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: false, staleTime: Infinity },
  },
});

// Both pages hang off one layout route so the bar and the breadcrumb survive a
// navigation.  `AppFrame` renders an
// `<Outlet/>` and nothing the pages read, which is what keeps the page tests --
// which mount `MatchListPage` and `MapStage` directly, with no router at all --
// independent of it.
const router = createBrowserRouter([
  {
    element: <AppFrame />,
    children: [
      { path: "/", element: <MatchListPage /> },
      { path: "/replay/:id", element: <ViewerPage /> },
    ],
  },
]);

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
}
