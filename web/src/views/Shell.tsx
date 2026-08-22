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
      <main className="page-body">{children}</main>
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
 */
export function Sentence({ children }: { children: ReactNode }) {
  return <p className="sentence">{children}</p>;
}
