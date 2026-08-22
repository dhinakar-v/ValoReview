/**
 * How a date and a duration are written, in one place.
 *
 * The two surfaces that show a capture's timestamp used to disagree about the
 * same fact.  The viewer header rendered `Replay.recorded_utc` raw --
 * `2026-05-28T02:27:37.075000+00:00`, microseconds and UTC offset included,
 * which is a machine's way of writing a date -- while the match list showed a
 * string Python had already formatted with `strftime` in `vrfhome/scan.py`.
 * Different type, different format, same field.
 *
 * So the server sends the ISO instant and the browser writes it, once, here.
 * That also puts it in the reader's **own** zone, which is the only zone they
 * can check against their memory of playing the match; a UTC offset on a local
 * capture is a fact about the recorder, not about the game.
 */

/** Written out in the reader's own zone, or a sentence when there is no date. */
export function formatRecorded(iso: string | null | undefined): string {
  if (!iso) {
    return NO_DATE;
  }
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    // Never the raw string as a fallback: an unparseable timestamp shown
    // verbatim is exactly the machine-readable smear this replaces.
    return NO_DATE;
  }
  return RECORDED.format(at);
}

/** Just the day, for a card that shows the time separately. */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) {
    return NO_DATE;
  }
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? NO_DATE : DAY.format(at);
}

/** Just the clock time, in the reader's zone. */
export function formatTimeOfDay(iso: string | null | undefined): string {
  if (!iso) {
    return "";
  }
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? "" : TIME.format(at);
}

/**
 * A length as `H:MM:SS` or `M:SS`.
 *
 * Not `clockText`: that one is the round clock and is always `M:SS`, because a
 * round cannot reach an hour.  A capture can.
 *
 * Truncated, not rounded, for the reason `clockText` gives about the other
 * direction: a capture 26:11.7 long has not reached 26:12, and a length is a
 * claim about how much of it there is.
 */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const seconds = total % 60;
  const minutes = Math.floor(total / 60) % 60;
  const hours = Math.floor(total / 3600);
  const mm = String(minutes).padStart(2, "0");
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${minutes}:${ss}`;
}

/** What a card says where the container held no timestamp at all. */
export const NO_DATE = "date not in file";

/*
 * Built once.  `Intl.DateTimeFormat` is expensive to construct and the match
 * list builds one of these per card per render.
 *
 * `undefined` for the locale on purpose: this is the reader's machine and
 * their own conventions are the right ones.  The parts are named rather than
 * taken from a `dateStyle`, because a numeric month is ambiguous across
 * exactly the two locales most likely to read this.
 */
const RECORDED = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const DAY = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const TIME = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
});
