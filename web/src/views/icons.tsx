/**
 * The icon set, and the one rule that keeps it from breaking the test suite.
 *
 * Every control on this page used to be a bare uppercase word, and the
 * transport bar was ASCII: `|<`, `<<`, `PLAY`, `>>`, `>|`.  Icons replace the
 * glyphs -- but they sit *beside* the words, never instead of them, and that
 * is not a style preference.
 *
 * There is not one `data-testid` in this repository.  Every DOM assertion in
 * `MapStage.test.tsx` and all three Playwright specs is text, ARIA role-name,
 * class or `title`: `getByRole("button", { name: "TRAILS", exact: true })`,
 * `findByText("DECODE POSITIONS")`, `findByText("SIGHT")`.  So the seven layer
 * and stage labels are an interface other files depend on, and an icon that
 * contributed to a button's accessible name would rename it.
 *
 * Hence `aria-hidden` and `focusable={false}` are applied *here*, centrally,
 * rather than at each call site: a decorative mark that a caller forgot to
 * hide is a test failure two files away from the change that caused it.
 *
 * Sizes are locked to two values.  14px is an icon inside a control, sitting
 * on the cap height of the label beside it; 16px is an icon standing alone.
 * Anything else is a one-off, and the old stylesheet's fifteen distinct
 * paddings are the argument against one-offs.
 */

import {
  ArrowLeft,
  ArrowLeftRight,
  ArrowUpRight,
  Bomb,
  Box,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  CircleAlert,
  CircleCheck,
  Coins,
  Cpu,
  Crosshair,
  Droplet,
  Eye,
  EyeOff,
  FileQuestion,
  Grid2x2,
  ImageOff,
  Keyboard,
  Layers as LayersGlyph,
  List,
  ListFilter,
  LoaderCircle,
  Map as MapGlyph,
  MapPin,
  Pause,
  Play,
  RefreshCw,
  Repeat,
  Route,
  Shield,
  SkipBack,
  SkipForward,
  Skull,
  Sparkles,
  Swords,
  Tag,
  Timer,
  TriangleAlert,
  Users,
  X,
  Zap,
  ZoomIn,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";

/** An icon inside a control, beside its label. */
export const ICON_INLINE = 14;
/** An icon standing on its own -- a status light, an empty state. */
export const ICON_ALONE = 16;

type Glyph = ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;

/**
 * Draw one glyph, decoratively.
 *
 * `aria-hidden` is not optional and is deliberately not a prop.  Where an icon
 * really is the only content -- a close button, a pager arrow -- the button
 * carries an `aria-label`, which is the accessible name the icon must not
 * compete with.
 */
export function Icon({
  glyph: Glyph,
  size = ICON_INLINE,
  className,
}: {
  glyph: Glyph;
  size?: number;
  className?: string;
}) {
  return (
    <Glyph
      size={size}
      strokeWidth={1.25}
      aria-hidden="true"
      focusable={false}
      className={className}
    />
  );
}

/** A spinner, which is the same glyph with the stylesheet's one animation. */
export function Spinner({ size = ICON_INLINE }: { size?: number }) {
  return <Icon glyph={LoaderCircle} size={size} className="spin" />;
}

export const glyphs = {
  // transport
  toStart: SkipBack,
  prevEvent: ChevronsLeft,
  play: Play,
  pause: Pause,
  nextEvent: ChevronsRight,
  toEnd: SkipForward,
  keys: Keyboard,
  loop: Repeat,
  timeline: List,
  clock: Timer,

  // layers
  view2d: Grid2x2,
  view3d: Box,
  utility: Zap,
  trails: Route,
  sight: Eye,
  callouts: Tag,
  layers: LayersGlyph,
  killMarkers: Crosshair,
  kills: Skull,
  ultimates: Sparkles,
  spike: Bomb,
  firstBlood: Droplet,
  zoom: ZoomIn,

  // The mark inside a primary button's trailing cap.  A direction rather
  // than a repeat of the button's own icon: the cap says the press leads
  // somewhere, the leading glyph says what the press is.
  capArrow: ArrowUpRight,

  // navigation and library
  back: ArrowLeft,
  map: MapGlyph,
  mapPin: MapPin,
  rescan: RefreshCw,
  filter: ListFilter,
  pagePrev: ChevronLeft,
  pageNext: ChevronRight,

  // viewer sections
  players: Users,
  rounds: Swords,
  casts: Sparkles,
  decode: Cpu,

  // status and absence
  ok: CircleCheck,
  bad: CircleAlert,
  simulated: TriangleAlert,
  noArt: ImageOff,
  noFile: FileQuestion,

  /*
    Roster and events.

    `atk` and `def` are two glyphs and not one, and that is the whole point:
    both sides used to be badged with `Shield`, which is the **defender's**
    mark.  Using it for ATK inverts the game's own iconography, which every
    player reads without thinking.  The attackers are the side that carries
    the spike, so they get the spike.
  */
  atk: Bomb,
  def: Shield,
  /*
    Show and hide, as an eye and a struck-through eye.

    This was `ListFilter` -- three descending bars -- on a control that filters
    nothing: it shows and hides five markers.  Two glyphs rather than one so
    the icon flips with the state, which is what makes the current state
    readable without hovering for the tooltip.
  */
  shown: Eye,
  hidden: EyeOff,
  credits: Coins,
  swap: ArrowLeftRight,
  close: X,
} satisfies Record<string, Glyph>;

/**
 * The wordmark.  Hand-drawn rather than imported, and inline `<svg>` rather
 * than `<img>` for a reason that is pinned by a test: `MatchList.test.tsx`
 * asserts `container.querySelector("img")` is null on the no-thumbnail state,
 * over the whole rendered tree.  A logo that happened to be an `<img>` would
 * fail an assertion about map thumbnails.
 *
 * It draws in `currentColor`, which `app.css` sets to `--brand` -- so the one
 * red in the app bar comes out of the generated palette like every other
 * colour here, and there is nothing to keep in step by hand.  **The exception
 * is `web/public/favicon.svg`**, which is fetched as a file before any CSS
 * exists and therefore hardcodes the same hex.  Change both.
 */
export function Wordmark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable={false}
    >
      {/*
        A scrub ring with a playhead on it and a play triangle inside: the two
        verbs in the name.  It replaced four horizontal timeline rules plus a
        head, which drew nine separate strokes -- at the 16px a browser tab
        actually renders, those collapsed into a grey smear.  A ring, a dot and
        a triangle are three shapes and survive the downscale.

        The gap at the top is 40 degrees and is what stops this reading as a
        loading spinner: a spinner's gap chases its head, and here the head sits
        still at the end of the track.
      */}
      <path d="M12 3.6A8.4 8.4 0 1 1 6.6 5.57" />
      <path
        d="M10.4 8.9 15.6 12 10.4 15.1Z"
        fill="currentColor"
        strokeWidth="1.4"
      />
      <circle cx="12" cy="3.6" r="2.1" fill="currentColor" strokeWidth="0" />
    </svg>
  );
}
