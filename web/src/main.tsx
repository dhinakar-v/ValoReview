import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import "./app.css";
import { MapReferencePage } from "./pages/MapReference";
import { MatchListPage } from "./pages/MatchList";
import { ViewerPage } from "./pages/Viewer";

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
const router = createBrowserRouter([
  { path: "/", element: <MatchListPage /> },
  { path: "/replay/:id", element: <ViewerPage /> },
  { path: "/map/:key", element: <MapReferencePage /> },
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
