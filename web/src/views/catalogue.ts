/**
 * The weapon catalogue, fetched once and shared.
 *
 * `GET /api/weapons` is a catalogue rather than a fact about a replay -- it
 * describes the game the way a radar image describes a map -- so it is keyed on
 * nothing and cached forever by the query client's `staleTime: Infinity`.
 * Every consumer (a roster card, the kill toast, a timeline row) asks for the
 * same list rather than one lookup per name, because there are twenty of them
 * and a feed that fetched per row would make a request per kill.
 *
 * An `assets/` with no `weapons/` answers with an empty list and its own
 * `source` line.  That is not an error and must not be rendered as one: the
 * callers fall back to the weapon's name in text, the same way a missing radar
 * falls back to a sentence.
 */

import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Weapon } from "../api/types";

export function useWeapons(): Weapon[] | undefined {
  const query = useQuery({
    queryKey: ["weapons"],
    queryFn: api.weapons,
    // A catalogue that is missing is an answer, not a failure worth retrying.
    retry: false,
  });
  return query.data?.weapons;
}
