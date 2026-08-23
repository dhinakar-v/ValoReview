using System.Text.Json;

namespace TransformSearch;

/// <summary>
/// One captured payload whose bit count is a whole number of 64-bit blocks.
/// </summary>
public sealed record Multi(byte[] Data, int Bits)
{
    public int Blocks => Bits / 64;
}

/// <summary>
/// The payloads of one seed that the 64-bit lane decodes on its own, whole.
///
/// A sweep over <c>mixed</c> is a sweep over one seed's keystream, so a corpus
/// for it is one seed's payloads and nothing else. The restriction to bit
/// counts that are a multiple of 64 is what lets the sweep run without the
/// other two lanes: <c>apply</c> runs 64-bit blocks while more than 63 bits
/// remain, so a payload of exactly n*64 bits never reaches the 32-bit lane, the
/// 8-bit lane or the tail XOR, and every one of its bits is decodable from the
/// lane already recovered.
///
/// It is also what makes the oracle exact, and that is the whole difference
/// between a sweep that ends and one that does not. A prefix of a longer
/// payload can only be checked for *not contradicting* a rep layout, which is
/// far too weak: a wrong keystream keeps 37% of one seed's payloads
/// individually and 2% of them together -- they are one actor replicating one
/// property layout, so they agree with each other rather than constraining each
/// other, and two per cent of 2^32 is eighty-six million survivors. A whole
/// payload must instead consume to **exactly** zero bits, which a wrong
/// keystream manages for 6 in 100,000. Measured on 12.10 seed 1492.
/// </summary>
public sealed class SeedCorpus
{
    public required uint Seed { get; init; }

    public required Multi[] Payloads { get; init; }

    /// <summary>
    /// The longest payload a sweep will read.
    ///
    /// Longer is a stronger check and a slower one, and the check is already
    /// decisive well below this: what the bound buys is that a candidate which
    /// contradicts the layout in block two costs two blocks rather than sixty.
    /// </summary>
    public const int MaxBits = 4096;

    public static SeedCorpus Load(string path, uint seed, int limit)
    {
        var seen = new HashSet<string>();
        var kept = new List<Multi>();

        foreach (var line in File.ReadLines(path))
        {
            if (line.Length == 0)
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            var bits = root.GetProperty("b").GetInt32();
            if (!Usable(bits) || root.GetProperty("s").GetUInt32() != seed)
            {
                continue;
            }

            var hex = root.GetProperty("p").GetString()!;
            if (!seen.Add(hex[..(bits / 4)]) || kept.Count >= limit)
            {
                continue;
            }

            kept.Add(new Multi(Convert.FromHexString(hex.AsSpan(0, bits / 4)), bits));
        }

        // Longest first. Every candidate pays for the first payload and almost
        // none reaches the second, so the first payload is both the sweep's
        // cost and its strength -- and strength wins, because a long payload is
        // rejected inside its second block just as fast as a short one and
        // constrains twenty states instead of one.
        kept.Sort((a, b) => b.Bits.CompareTo(a.Bits));
        return new SeedCorpus { Seed = seed, Payloads = [.. kept] };
    }

    public static bool Usable(int bits) => bits >= 128 && bits <= MaxBits && bits % 64 == 0;

    /// <summary>
    /// How many payloads of a seed a sweep stages, which is what the ranking
    /// counts states over. It is the default for <c>--stage-n</c> and the two
    /// have to agree, or a seed is picked for payloads the sweep never reads.
    /// </summary>
    public const int StagedPayloads = 8;

    /// <summary>
    /// The seeds worth sweeping: those whose payloads open as rep layouts,
    /// ranked by how many unknown keystream states those payloads exercise.
    ///
    /// Two things decide a seed and neither is how busy the actor is. The first
    /// block needs no keystream -- it is keyed by the seed itself -- so whether
    /// a payload is a property chain at all can be read before any candidate is
    /// tried, and it has to be: ranking on payload count alone picks the
    /// busiest actor in the capture, which on 12.10 is a seed whose eighty-nine
    /// payloads are ClassNetCache blobs, and a sweep over it correctly keeps
    /// nothing after three minutes of work.
    ///
    /// The second is length. What a candidate has to survive is one state per
    /// block past the first, so a 22-block payload is twenty-one constraints
    /// and a 128-bit payload is one. On 13.04 the seed with the most whole
    /// payloads carries five of 128 bits, and sweeping it keeps millions;
    /// the seed this ranking picks carries five of 1,408 bits and keeps a
    /// handful.
    /// </summary>
    public static (uint Seed, int Count, int States)[] RankSeeds(string path, Lane lane, int minPayloads)
    {
        var perSeed = new Dictionary<uint, HashSet<string>>();

        foreach (var line in File.ReadLines(path))
        {
            if (line.Length == 0)
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            var bits = root.GetProperty("b").GetInt32();
            if (!Usable(bits))
            {
                continue;
            }

            var seed = root.GetProperty("s").GetUInt32();
            if (!perSeed.TryGetValue(seed, out var payloads))
            {
                payloads = [];
                perSeed[seed] = payloads;
            }

            payloads.Add(root.GetProperty("p").GetString()![..(bits / 4)]);
        }

        var rows = new List<(uint Seed, int Count, int States)>();
        foreach (var (seed, payloads) in perSeed)
        {
            if (payloads.Count < minPayloads)
            {
                continue;
            }

            // Every one of them, not most: a seed mixing chains with blobs
            // would stage a payload no keystream can decode whole, and the
            // sweep requires every staged payload to decode.
            var opens = payloads.All(hex => OpensCleanly(
                lane.Apply(BitConverter.ToUInt64(Convert.FromHexString(hex.AsSpan(0, 16))), seed),
                hex.Length * 4));
            if (opens)
            {
                // One state per block past the first, over the payloads a sweep
                // would actually stage.
                var states = payloads
                    .Select(hex => (hex.Length * 4 / 64) - 1)
                    .OrderByDescending(n => n)
                    .Take(StagedPayloads)
                    .Sum();
                rows.Add((seed, payloads.Count, states));
            }
        }

        return [.. rows.OrderByDescending(r => r.States)];
    }

    /// <summary>
    /// Whether a decoded first block contradicts a rep layout, asked of the one
    /// block that needs no keystream.
    ///
    /// <see cref="Framing.OpensAsChain"/> asks whether one pair parses, which
    /// is the right question for a composition search and the wrong one here:
    /// on 12.10 it accepts the seed whose eighty-nine payloads open
    /// <c>handle 495, length 2</c> then <c>handle 72</c> -- a handle that
    /// descends, so the block is not a chain -- and a sweep over that seed
    /// keeps nothing after three minutes. What separates the seeds that work is
    /// not how much parses but whether anything contradicts: handles ascend,
    /// and no field claims more bits than the payload holds.
    ///
    /// Running out of block is not a contradiction. The block is a 64-bit
    /// window onto a longer payload and stopping mid-pair is how it ends.
    /// </summary>
    public static bool OpensCleanly(ulong block, int bits)
    {
        var pos = 1;
        var previousHandle = 0u;

        while (true)
        {
            if (!TryReadPacked(block, ref pos, out var handle))
            {
                return true;
            }

            if (handle == 0)
            {
                return pos == bits;
            }

            if (handle <= previousHandle)
            {
                return false;
            }

            if (!TryReadPacked(block, ref pos, out var fieldBits))
            {
                return true;
            }

            if (fieldBits == 0 || fieldBits > (uint)bits)
            {
                return false;
            }

            previousHandle = handle;
            pos += (int)fieldBits;
            if (pos >= 64)
            {
                return pos <= bits;
            }
        }
    }

    private static bool TryReadPacked(ulong block, ref int pos, out uint value)
    {
        value = 0;
        var shift = 0;
        while (true)
        {
            if (pos + 8 > 64 || shift >= 32)
            {
                return false;
            }

            var group = (uint)((block >> pos) & 0xFF);
            pos += 8;
            value |= (group >> 1) << shift;
            shift += 7;
            if ((group & 1) == 0)
            {
                return true;
            }
        }
    }
}

/// <summary>
/// Whether a payload decodes to a UE backwards-compatible rep layout that
/// consumes every one of its bits: one bit, then <c>SerializeIntPacked</c>
/// (handle, num_bits) pairs with strictly ascending handles, terminated by a
/// zero handle exactly at the end.
///
/// Blocks are decoded as the parse reaches them rather than up front, which is
/// most of what makes a sweep affordable: a wrong keystream contradicts the
/// layout inside the second block almost always, and decoding sixty blocks to
/// discover that would cost thirty times what discovering it costs.
/// </summary>
public static class ExactChain
{
    public static bool Holds(Multi payload, Lane lane, uint[] states, byte[] buffer)
    {
        var bits = payload.Bits;
        var decoded = 0;
        var pos = 1;
        var previousHandle = 0u;

        while (true)
        {
            if (!TryReadPacked(payload, lane, states, buffer, ref decoded, ref pos, out var handle))
            {
                return false;
            }

            if (handle == 0)
            {
                return pos == bits;
            }

            if (handle <= previousHandle)
            {
                return false;
            }

            if (!TryReadPacked(payload, lane, states, buffer, ref decoded, ref pos, out var fieldBits))
            {
                return false;
            }

            // A field longer than the payload that holds it is a parse failure
            // rather than a large field, and the payload's own bit count is the
            // only bound that needs stating.
            if (fieldBits == 0 || fieldBits > (uint)bits)
            {
                return false;
            }

            previousHandle = handle;
            pos += (int)fieldBits;
            if (pos > bits)
            {
                return false;
            }
        }
    }

    private static bool TryReadPacked(
        Multi payload,
        Lane lane,
        uint[] states,
        byte[] buffer,
        ref int decoded,
        ref int pos,
        out uint value)
    {
        value = 0;
        var shift = 0;
        while (true)
        {
            if (pos + 8 > payload.Bits || shift >= 32)
            {
                return false;
            }

            var index = pos >> 3;
            var offset = pos & 7;
            Ensure(payload, lane, states, buffer, ref decoded, (index + (offset == 0 ? 0 : 1)) / 8);

            uint group = buffer[index];
            if (offset != 0)
            {
                group = ((group >> offset) | ((uint)buffer[index + 1] << (8 - offset))) & 0xFF;
            }

            pos += 8;
            value |= (group >> 1) << shift;
            shift += 7;
            if ((group & 1) == 0)
            {
                return true;
            }
        }
    }

    private static void Ensure(
        Multi payload,
        Lane lane,
        uint[] states,
        byte[] buffer,
        ref int decoded,
        int block)
    {
        while (decoded <= block && decoded < payload.Blocks)
        {
            var value = lane.Apply(BitConverter.ToUInt64(payload.Data, decoded * 8), states[decoded]);
            BitConverter.TryWriteBytes(buffer.AsSpan(decoded * 8, 8), value);
            decoded++;
        }
    }
}
