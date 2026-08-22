/**
 * The frame every page sits in, and the two states every page can be in.
 *
 * `Loading` and `Failed` are here rather than inlined so that a failure always
 * looks the same and always says what the server said.  `ApiError` carries the
 * server's own `detail`, and the whole point of that detail is that it names
 * the thing that went wrong -- showing "something went wrong" instead would
 * throw away the one sentence worth reading.
 */

import type { ReactNode } from "react";

import { ApiError } from "../api/client";

export function Page({
  title,
  actions,
  footer,
  children,
}: {
  title: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="page">
      <header className="page-head">
        <h1>{title}</h1>
        <div className="spacer" />
        {actions}
      </header>
      {/*
        `id` and `tabIndex` exist for the skip link in `AppFrame`.  A skip link
        that only moves the *scroll* leaves the focus back up in the bar, so
        the next Tab press returns to the first thing it was meant to skip --
        which is the failure mode that makes people decide skip links do not
        work.  -1 keeps it out of the tab order otherwise.
      */}
      <main className="page-body" id="main" tabIndex={-1}>
        {children}
      </main>
      {footer ? <footer className="page-foot">{footer}</footer> : null}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="muted">Reading {what}…</p>;
}

export function Failed({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError || error instanceof Error
      ? error.message
      : String(error);
  return <p className="error">{message}</p>;
}

/**
 * A sentence in the place a picture would go.
 *
 * Deliberately not a fallback drawing of any kind.  A diagram where a map
 * belongs reads as a map however it is captioned, so the two things that can be
 * absent -- the decode and the radar image -- each get words instead.
 *
 * `ui.EmptyState` wraps this and puts a mark above it.  That mark is allowed
 * where a drawing is not, and the difference is the whole argument: a
 * crossed-out picture frame reads as *there is no picture*, which is the claim
 * being made, whereas a schematic of the map reads as the map.
 */
export function Sentence({ children }: { children: ReactNode }) {
  return <p className="sentence">{children}</p>;
}
