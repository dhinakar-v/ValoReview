import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import "./app.css";
import { MapReferencePage } from "./pages/MapReference";
import { MatchListPage } from "./pages/MatchList";
import { ViewerPage } from "./pages/Viewer";
import { AppFrame } from "./views/AppFrame";

// A local server reading files off a disk: nothing here goes stale on its own,
// so refetching on window focus is pure noise. A rescan is a button.
const client = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: false, staleTime: Infinity },
  },
});

// `/map/:key` is its own route on purpose. The desktop map reference is handed
// no Replay because it describes the map and not the match -- the same picture
// for every capture on Bind -- and a route that only ever receives a map key is
// how that guarantee survives becoming a URL.
//
// The three pages hang off one layout route so the bar, the breadcrumb, the
// decoder light and the sound toggle survive a navigation.  `AppFrame` renders
// an `<Outlet/>` and nothing the pages read, which is what keeps the page tests
// -- which mount `MatchListPage` and `MapStage` directly, with no router at all
// -- independent of it.
const router = createBrowserRouter([
  {
    element: <AppFrame />,
    children: [
      { path: "/", element: <MatchListPage /> },
      { path: "/replay/:id", element: <ViewerPage /> },
      { path: "/map/:key", element: <MapReferencePage /> },
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
