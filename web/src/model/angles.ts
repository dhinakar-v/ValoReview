/**
 * The two lines of arithmetic that a port of this model gets wrong.
 *
 * They live in their own file because both of them fail *plausibly*.  Neither
 * throws, neither draws nothing, neither looks obviously broken -- each puts a
 * marker somewhere believable and slightly wrong, which is the expensive kind
 * of bug and the reason `tests/golden/track_at.json` exists.
 */

/**
 * Python's float remainder, not JavaScript's, and not `((a % n) + n) % n`.
 *
 * **Python's `%` takes the sign of the divisor; JavaScript's takes the sign of
 * the dividend.**  `(-350 + 180) % 360` is `190` in Python and `-170` here.
 * Every remainder in this model is a Python one, so every one of them goes
 * through this.
 *
 * The obvious correction, `((value % by) + by) % by`, gets the sign right and
 * the *value* subtly wrong: it is three operations where Python does one, and
 * `9.8 + 360` then `% 360` comes back as `9.800000000000011`.  That is a
 * hundredth of a degree, it never looks wrong on screen, and it is exactly the
 * kind of drift the golden fixtures exist to refuse.  So this is CPython's
 * `float_rem` instead: take `fmod`, which is what JavaScript's `%` already is,
 * and correct the sign only when it actually differs -- including the zero
 * case, where CPython returns a zero carrying the divisor's sign.
 */
export function mod(value: number, by: number): number {
  const remainder = value % by;
  if (remainder !== 0) {
    return by < 0 !== remainder < 0 ? remainder + by : remainder;
  }
  return by < 0 ? -0 : 0;
}

/**
 * Degrees to radians, multiplied the way `math.radians` multiplies.
 *
 * CPython holds `pi / 180` as a constant and multiplies by it; writing
 * `(degrees * Math.PI) / 180` instead rounds twice in a different order and
 * lands a bit or two away.  On its own that is nothing -- but a sight ray is
 * marched cell by cell against a 256-wide mask, so a last-bit difference in
 * the angle can stop a ray one cell earlier and move a whole polygon vertex.
 */
const DEG_TO_RAD = Math.PI / 180;

export function radians(degrees: number): number {
  return degrees * DEG_TO_RAD;
}

/** Linear interpolation, in the same order of operations as `model._lerp`. */
export function lerp(a: number, b: number, f: number): number {
  return a + (b - a) * f;
}

/**
 * Shortest arc between two angles in degrees, for yaw **and** for pitch.
 *
 * A heading going 350 -> 10 has moved 20 degrees forward, not 340 back.  With
 * JavaScript's own `%` the delta comes out negative and the marker spins the
 * long way round for a few frames, which reads as a canvas problem rather than
 * an arithmetic one and gets blamed accordingly.
 *
 * Pitch goes through this too, and that is measured rather than tidy: pitch is
 * the same kind of quantity off the same packed angle dword, so a player a
 * degree above the horizon is at 1.0 and a degree below is at 359.0, and
 * interpolating those linearly lands at 180 -- pointing backwards, at the exact
 * moment somebody flicks across the horizon.  See `vrfview.model._lerp_angle`.
 */
export function lerpAngle(a: number, b: number, f: number): number {
  const delta = mod(b - a + 180, 360) - 180;
  return mod(a + delta * f, 360);
}
