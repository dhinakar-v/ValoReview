namespace TransformSearch;

/// <summary>
/// First blocks that are known to be real plaintext, as a known-plaintext
/// oracle for a build whose transform is unknown.
///
/// The set is built by decoding captures whose transforms *are* published and
/// keeping the first block of each payload. It works because the plaintext is
/// engine framing rather than build-specific ciphertext: two captures on
/// different patches and different maps, each correctly decoded, share about
/// 6% of their distinct first blocks -- the same standard property updates
/// replicated in both matches.
///
/// What makes it worth having is the floor underneath it. Decoding a capture
/// with a transform published for a *different* build -- a decode known to be
/// wrong -- and intersecting against this set returns **zero**, not a few
/// stragglers, because an exact 64-bit collision between two unrelated
/// bijections does not happen at these sample sizes. So a hit is evidence in a
/// way that a bit-bias score is not: the bias mask separates two populations by
/// several sigma, where this separates them by everything.
/// </summary>
public sealed class KnownPlaintext
{
    private readonly HashSet<ulong> blocks;

    private KnownPlaintext(HashSet<ulong> blocks) => this.blocks = blocks;

    public int Count => blocks.Count;

    /// <summary>One 16-digit hex block per line; blank lines ignored.</summary>
    public static KnownPlaintext Load(string path)
    {
        var set = new HashSet<ulong>();
        foreach (var line in File.ReadLines(path))
        {
            var text = line.Trim();
            if (text.Length == 0)
            {
                continue;
            }

            set.Add(Convert.ToUInt64(text, 16));
        }

        return new KnownPlaintext(set);
    }

    public int Hits(ulong[] decoded)
    {
        var hits = 0;
        foreach (var value in decoded)
        {
            if (blocks.Contains(value))
            {
                hits++;
            }
        }

        return hits;
    }
}
