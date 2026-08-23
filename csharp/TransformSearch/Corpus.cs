using System.Text.Json;

namespace TransformSearch;

/// <summary>
/// The captured payloads, reduced to what a first-block search needs.
///
/// Only the first 64 bits of each payload are used, and only payloads that
/// have a whole one. That restriction is what makes the search possible at
/// all: <c>apply</c> sets <c>state = seed</c> and advances the keystream only
/// afterwards, so the first block is keyed by a value that is plaintext in the
/// bunch header. Every later block depends on the four constants as well, and
/// those are a separate and much cheaper problem.
/// </summary>
public sealed class Corpus
{
    /// <summary>Ciphertext first blocks, little-endian.</summary>
    public required ulong[] Values { get; init; }

    /// <summary><c>rotr32(state, k)</c> zero-extended, at <c>i * Ops.Stride + (k - 1)</c>.</summary>
    public required ulong[] Ror { get; init; }

    /// <summary><c>(ror_k % 63) + 1</c>, the rotate distance, at <c>i * Ops.Stride + (k - 1)</c>.</summary>
    public required int[] Amt { get; init; }

    public int Count => Values.Length;

    /// <summary>How many lines the file held, before deduplication.</summary>
    public required int LinesRead { get; init; }

    /// <summary>
    /// Load, keeping payloads with a full 64-bit first block and discarding
    /// repeats.
    ///
    /// Deduplication is not an optimisation. The replication stream re-sends
    /// the same payload thousands of times -- one capture's 200,000 lines hold
    /// about 46,000 distinct first blocks -- so scoring the raw file would
    /// measure how often one packet repeats rather than what a payload looks
    /// like, and a handful of hot packets would decide the whole search.
    /// </summary>
    public static Corpus Load(string path, int limit)
    {
        var seen = new HashSet<(uint Seed, ulong Value)>();
        var values = new List<ulong>();
        var seeds = new List<uint>();
        var lines = 0;

        foreach (var line in File.ReadLines(path))
        {
            lines++;
            if (line.Length == 0)
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            if (root.GetProperty("b").GetInt32() < 64)
            {
                continue;
            }

            var seed = root.GetProperty("s").GetUInt32();
            var hex = root.GetProperty("p").GetString()!;
            var value = BitConverter.ToUInt64(Convert.FromHexString(hex.AsSpan(0, 16)));

            if (!seen.Add((seed, value)) || values.Count >= limit)
            {
                continue;
            }

            values.Add(value);
            seeds.Add(seed);
        }

        var n = values.Count;
        var ror = new ulong[n * Ops.Stride];
        var amt = new int[n * Ops.Stride];
        for (var i = 0; i < n; i++)
        {
            for (var k = 1; k <= Ops.Stride; k++)
            {
                var r = Ops.RotR32(seeds[i], k);
                ror[(i * Ops.Stride) + k - 1] = r;
                amt[(i * Ops.Stride) + k - 1] = (int)((r % 63) + 1);
            }
        }

        return new Corpus
        {
            Values = [.. values],
            Ror = ror,
            Amt = amt,
            LinesRead = lines,
        };
    }

    /// <summary>A prefix of this corpus, for the cheap stage of a two-stage score.</summary>
    public Corpus Take(int n)
    {
        n = Math.Min(n, Count);
        return new Corpus
        {
            Values = Values[..n],
            Ror = Ror[..(n * Ops.Stride)],
            Amt = Amt[..(n * Ops.Stride)],
            LinesRead = LinesRead,
        };
    }
}
