namespace TransformSearch;

/// <summary>One build's four keystream constants, as a transform class carries them.</summary>
public sealed record BuildConstants(uint SeedAddend, uint InitAOffset, bool InitAAdds, byte TailXor)
{
    public override string ToString() =>
        $"seed_addend = 0x{SeedAddend:X8}, init_a_offset = 0x{InitAOffset:X2}, "
        + $"init_a_adds = {(InitAAdds ? "True" : "False")}, tail_xor = 0x{TailXor:X2}";
}

/// <summary>
/// The constants, from two seeds whose <c>mixed</c> a sweep has recovered.
///
/// <c>_initial_prng_a</c> computes
/// <code>
/// mixed = (((sp &gt;&gt; 15) ^ sp) &gt;&gt; 12) ^ ((seed -+ off) * 0x02000000) ^ sp
/// </code>
/// with <c>sp = seed + seed_addend</c>. The middle term is a shift left by 25,
/// so only the low **seven** bits of <c>seed -+ off</c> reach the result: that
/// whole term has 128 possible values rather than 2^32, and the rest of the
/// expression inverts exactly. So one seed leaves 128 candidate pairs per sign
/// and a second seed picks out the one that explains both.
///
/// <c>tail_xor</c> is the low byte of <c>seed_addend</c> in all five published
/// builds. It is reported as a cross-check and never as a derivation -- an
/// unverified byte that decodes the last bits of every short payload would be a
/// plausible wrong answer of exactly the kind this project refuses.
/// </summary>
public static class Solve
{
    /// <summary>
    /// The constants one seed's <c>mixed</c> admits: 128 low-bit residues per
    /// sign, and nothing narrower, because the shift left by 25 discards
    /// everything above the low seven bits of <c>seed -+ init_a_offset</c>.
    ///
    /// A second seed is what picks one out. It can do that two ways -- by
    /// having its own <c>mixed</c> swept, or by simply being decoded under each
    /// candidate, which is cheaper and needs no second sweep at all.
    /// </summary>
    public static IEnumerable<BuildConstants> Candidates(uint seed, uint mixed)
    {
        foreach (var adds in new[] { false, true })
        {
            for (uint low = 0; low < 128; low++)
            {
                var seedPlus = Keystream.Unmix(mixed ^ (low << 25));
                var seedAddend = seedPlus - seed;
                var offset = (adds ? low - seed : seed - low) & 0x7F;
                var candidate = new BuildConstants(seedAddend, offset, adds, (byte)(seedAddend & 0xFF));
                if (Keystream.Mixed(seed, seedAddend, offset, adds) == mixed)
                {
                    yield return candidate;
                }
            }
        }
    }

    public static List<BuildConstants> FromMixed(IReadOnlyList<(uint Seed, uint Mixed)> observations)
    {
        if (observations.Count < 2)
        {
            throw new ArgumentException("two seeds are needed to pin the offset and its sign");
        }

        var found = new List<BuildConstants>();
        var (firstSeed, firstMixed) = observations[0];

        foreach (var adds in new[] { false, true })
        {
            for (uint low = 0; low < 128; low++)
            {
                var term = low << 25;
                var seedPlus = Keystream.Unmix(firstMixed ^ term);
                var seedAddend = seedPlus - firstSeed;

                // The low seven bits of (seed -+ off) are what survived the
                // shift, so they name the offset modulo 128. Published offsets
                // are all below 0x25, so the residue is the offset itself --
                // and a build whose offset exceeded 127 would show up as a
                // candidate that fails the second seed rather than as a
                // silently wrong answer.
                var offset = adds ? low - firstSeed : firstSeed - low;
                offset &= 0x7F;

                var candidate = new BuildConstants(
                    seedAddend,
                    offset,
                    adds,
                    (byte)(seedAddend & 0xFF));

                if (!Explains(candidate, observations))
                {
                    continue;
                }

                if (!found.Any(c => c == candidate))
                {
                    found.Add(candidate);
                }
            }
        }

        return found;
    }

    private static bool Explains(BuildConstants candidate, IReadOnlyList<(uint Seed, uint Mixed)> observations)
    {
        foreach (var (seed, mixed) in observations)
        {
            if (Keystream.Mixed(seed, candidate.SeedAddend, candidate.InitAOffset, candidate.InitAAdds) != mixed)
            {
                return false;
            }
        }

        return true;
    }
}
