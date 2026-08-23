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
 *
 * The set is Phosphor's, drawn at its **fill** weight, which is a solid shape
 * carrying no stroke -- so there is no line width to set here, and what `Icon`
 * pins in its place is `weight`.  The `*Icon`-suffixed exports are the current
 * names; the bare ones the package still ships are deprecated.
 *
 * The glyphs are imported one module at a time rather than from the package
 * barrel, which re-exports three thousand of them: through the barrel a single
 * test file spent 4.29s collecting, and 0.37s importing the forty-five it
 * actually draws.  The two types below come from the barrel because a type
 * import is erased and costs nothing.
 */

import { ArrowLeftIcon } from "@phosphor-icons/react/dist/csr/ArrowLeft";
import { ArrowUpRightIcon } from "@phosphor-icons/react/dist/csr/ArrowUpRight";
import { ArrowsClockwiseIcon } from "@phosphor-icons/react/dist/csr/ArrowsClockwise";
import { ArrowsLeftRightIcon } from "@phosphor-icons/react/dist/csr/ArrowsLeftRight";
import { BombIcon } from "@phosphor-icons/react/dist/csr/Bomb";
import { CaretDoubleLeftIcon } from "@phosphor-icons/react/dist/csr/CaretDoubleLeft";
import { CaretDoubleRightIcon } from "@phosphor-icons/react/dist/csr/CaretDoubleRight";
import { CaretLeftIcon } from "@phosphor-icons/react/dist/csr/CaretLeft";
import { CaretRightIcon } from "@phosphor-icons/react/dist/csr/CaretRight";
import { CheckCircleIcon } from "@phosphor-icons/react/dist/csr/CheckCircle";
import { CircleNotchIcon } from "@phosphor-icons/react/dist/csr/CircleNotch";
import { CoinsIcon } from "@phosphor-icons/react/dist/csr/Coins";
import { CpuIcon } from "@phosphor-icons/react/dist/csr/Cpu";
import { CrosshairIcon } from "@phosphor-icons/react/dist/csr/Crosshair";
import { CubeIcon } from "@phosphor-icons/react/dist/csr/Cube";
import { DropIcon } from "@phosphor-icons/react/dist/csr/Drop";
import { EyeIcon } from "@phosphor-icons/react/dist/csr/Eye";
import { EyeSlashIcon } from "@phosphor-icons/react/dist/csr/EyeSlash";
import { FileXIcon } from "@phosphor-icons/react/dist/csr/FileX";
import { FunnelSimpleIcon } from "@phosphor-icons/react/dist/csr/FunnelSimple";
import { GridFourIcon } from "@phosphor-icons/react/dist/csr/GridFour";
import { ImageBrokenIcon } from "@phosphor-icons/react/dist/csr/ImageBroken";
import { KeyboardIcon } from "@phosphor-icons/react/dist/csr/Keyboard";
import { LightningIcon } from "@phosphor-icons/react/dist/csr/Lightning";
import { ListIcon } from "@phosphor-icons/react/dist/csr/List";
import { MagnifyingGlassPlusIcon } from "@phosphor-icons/react/dist/csr/MagnifyingGlassPlus";
import { MapPinIcon } from "@phosphor-icons/react/dist/csr/MapPin";
import { MapTrifoldIcon } from "@phosphor-icons/react/dist/csr/MapTrifold";
import { PathIcon } from "@phosphor-icons/react/dist/csr/Path";
import { PauseIcon } from "@phosphor-icons/react/dist/csr/Pause";
import { PlayIcon } from "@phosphor-icons/react/dist/csr/Play";
import { RepeatIcon } from "@phosphor-icons/react/dist/csr/Repeat";
import { ShieldIcon } from "@phosphor-icons/react/dist/csr/Shield";
import { SkipBackIcon } from "@phosphor-icons/react/dist/csr/SkipBack";
import { SkipForwardIcon } from "@phosphor-icons/react/dist/csr/SkipForward";
import { SkullIcon } from "@phosphor-icons/react/dist/csr/Skull";
import { SparkleIcon } from "@phosphor-icons/react/dist/csr/Sparkle";
import { StackIcon } from "@phosphor-icons/react/dist/csr/Stack";
import { SwordIcon } from "@phosphor-icons/react/dist/csr/Sword";
import { TagIcon } from "@phosphor-icons/react/dist/csr/Tag";
import { TimerIcon } from "@phosphor-icons/react/dist/csr/Timer";
import { UsersIcon } from "@phosphor-icons/react/dist/csr/Users";
import { WarningCircleIcon } from "@phosphor-icons/react/dist/csr/WarningCircle";
import { WarningIcon } from "@phosphor-icons/react/dist/csr/Warning";
import { XIcon } from "@phosphor-icons/react/dist/csr/X";
import type { Icon as PhosphorGlyph, IconWeight } from "@phosphor-icons/react";

/** An icon inside a control, beside its label. */
export const ICON_INLINE = 14;
/** An icon standing on its own -- a status light, an empty state. */
export const ICON_ALONE = 16;

/**
 * One glyph, as the icon set publishes it.  Exported so `ui.tsx` and the menus
 * type their `icon` props against this rather than against a structural copy
 * that could drift from what the package actually accepts.
 */
export type Glyph = PhosphorGlyph;

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
  weight = "fill",
  className,
}: {
  glyph: Glyph;
  size?: number;
  weight?: IconWeight;
  className?: string;
}) {
  return (
    <Glyph
      size={size}
      weight={weight}
      aria-hidden="true"
      focusable={false}
      className={className}
    />
  );
}

/** A spinner, which is the same glyph with the stylesheet's one animation. */
export function Spinner({ size = ICON_INLINE }: { size?: number }) {
  return <Icon glyph={CircleNotchIcon} size={size} className="spin" />;
}

export const glyphs = {
  // transport
  toStart: SkipBackIcon,
  prevEvent: CaretDoubleLeftIcon,
  play: PlayIcon,
  pause: PauseIcon,
  nextEvent: CaretDoubleRightIcon,
  toEnd: SkipForwardIcon,
  keys: KeyboardIcon,
  loop: RepeatIcon,
  timeline: ListIcon,
  clock: TimerIcon,

  // layers
  view2d: GridFourIcon,
  view3d: CubeIcon,
  utility: LightningIcon,
  trails: PathIcon,
  sight: EyeIcon,
  callouts: TagIcon,
  layers: StackIcon,
  killMarkers: CrosshairIcon,
  kills: SkullIcon,
  ultimates: SparkleIcon,
  spike: BombIcon,
  firstBlood: DropIcon,
  zoom: MagnifyingGlassPlusIcon,

  // The mark inside a primary button's trailing cap.  A direction rather
  // than a repeat of the button's own icon: the cap says the press leads
  // somewhere, the leading glyph says what the press is.
  capArrow: ArrowUpRightIcon,

  // navigation and library
  back: ArrowLeftIcon,
  map: MapTrifoldIcon,
  mapPin: MapPinIcon,
  rescan: ArrowsClockwiseIcon,
  filter: FunnelSimpleIcon,
  pagePrev: CaretLeftIcon,
  pageNext: CaretRightIcon,

  // viewer sections
  players: UsersIcon,
  rounds: SwordIcon,
  casts: SparkleIcon,
  decode: CpuIcon,

  // status and absence
  ok: CheckCircleIcon,
  bad: WarningCircleIcon,
  simulated: WarningIcon,
  noArt: ImageBrokenIcon,
  noFile: FileXIcon,

  /*
    Roster and events.

    `atk` and `def` are two glyphs and not one, and that is the whole point:
    both sides used to be badged with `Shield`, which is the **defender's**
    mark.  Using it for ATK inverts the game's own iconography, which every
    player reads without thinking.  The attackers are the side that carries
    the spike, so they get the spike.
  */
  atk: BombIcon,
  def: ShieldIcon,
  /*
    Show and hide, as an eye and a struck-through eye.

    This was the filter glyph -- descending bars -- on a control that filters
    nothing: it shows and hides five markers.  Two glyphs rather than one so
    the icon flips with the state, which is what makes the current state
    readable without hovering for the tooltip.
  */
  shown: EyeIcon,
  hidden: EyeSlashIcon,
  credits: CoinsIcon,
  swap: ArrowsLeftRightIcon,
  close: XIcon,
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
