using System.Numerics;
using System.Text.Json;

namespace TransformSearch;

/// <summary>
/// A build's 32-bit lane, applied to a single value.
///
/// Same vocabulary as the 64-bit lane at half the width, with two differences
/// that every published build shares: the state operand is
/// <c>rotl32(state, k)</c> where the 64-bit lane takes <c>rotr32(state, k)</c>,
/// and a rotate distance is <c>(operand % 31) + 1</c> rather than
/// <c>% 63</c>.
/// </summary>
public sealed class Lane32(Candidate candidate)
{
    private readonly int[] kinds = candidate.Kinds;
    private readonly int[] ks = candidate.Ks;

    public uint Apply(uint value, uint state)
    {
        for (var d = 0; d < kinds.Length; d++)
        {
            var k = Math.Max(ks[d], 1);
            var rol = BitOperations.RotateLeft(state, k);
            value = kinds[d] switch
            {
                Ops.Swap => ((value & 0x55555555u) << 1) | ((value >> 1) & 0x55555555u),
                Ops.Reverse => Reverse32(value),
                Ops.Sbox => Substitute32(value),
                Ops.Not => ~value,
                Ops.Add => value + rol,
                Ops.Sub => value - rol,
                Ops.Xor => value ^ rol,
                Ops.XorNot => value ^ ~rol,
                Ops.RotR => BitOperations.RotateRight(value, (int)((rol % 31) + 1)),
                Ops.RotL => BitOperations.RotateLeft(value, (int)((rol % 31) + 1)),
                _ => throw new ArgumentOutOfRangeException(nameof(state)),
            };
        }

        return value;
    }

    private static uint Reverse32(uint v)
    {
        v = ((v & 0x55555555u) << 1) | ((v >> 1) & 0x55555555u);
        v = ((v & 0x33333333u) << 2) | ((v >> 2) & 0x33333333u);
        v = ((v & 0x0F0F0F0Fu) << 4) | ((v >> 4) & 0x0F0F0F0Fu);
        v = ((v & 0x00FF00FFu) << 8) | ((v >> 8) & 0x00FF00FFu);
        return (v << 16) | (v >> 16);
    }

    private static uint Substitute32(uint v)
    {
        var t = Tables.Substitute32;
        return t[(int)(v & 0xFF)]
             | ((uint)t[(int)((v >> 8) & 0xFF)] << 8)
             | ((uint)t[(int)((v >> 16) & 0xFF)] << 16)
             | ((uint)t[(int)((v >> 24) & 0xFF)] << 24);
    }
}

/// <summary>
/// The payloads that pin a 32-bit lane: a whole number of 64-bit blocks and
/// then exactly one 32-bit block.
///
/// <c>apply</c> runs 32-bit blocks while more than 31 bits remain and 8-bit
/// blocks while more than 7 do, so a bit count 32 past a multiple of 64 reaches
/// the 32-bit lane once and stops -- no 8-bit block, no tail XOR. With the
/// keystream recovered, the 32-bit lane is the only unknown such a payload has.
/// </summary>
public sealed record Tail32(byte[] Data, int Bits, uint Seed)
{
    public int Blocks => Bits / 64;

    public static List<Tail32> Load(string path, int limit)
    {
        var seen = new HashSet<string>();
        var kept = new List<Tail32>();

        foreach (var line in File.ReadLines(path))
        {
            if (line.Length == 0)
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            var bits = root.GetProperty("b").GetInt32();
            if (bits % 64 != 32 || bits < 96 || bits > SeedCorpus.MaxBits)
            {
                continue;
            }

            var seed = root.GetProperty("s").GetUInt32();
            var hex = root.GetProperty("p").GetString()![..(bits / 4)];
            if (!seen.Add($"{seed}:{hex}") || kept.Count >= limit)
            {
                continue;
            }

            kept.Add(new Tail32(Convert.FromHexString(hex), bits, seed));
        }

        return kept;
    }
}

/// <summary>
/// The 32-bit lanes a recovered 64-bit lane makes plausible, and how many
/// payloads each decodes whole.
///
/// The neighbourhood is small and it is not a guess: every published pair
/// shares its operation order and its operand order, and what differs is where
/// a complement sits, because a <c>~</c> applies to a 32-bit intermediate in one
/// and a 64-bit one in the other. So each xor may or may not carry its
/// complement, and a <c>not</c> may be inserted at any one position. Recovering
/// 12.10's and 12.11's published lanes takes the first kind of variation and
/// 13.00's takes the second.
/// </summary>
public static class Lane32Search
{
    public static IEnumerable<Candidate> Variants(Candidate lane)
    {
        var xors = new List<int>();
        for (var i = 0; i < lane.Depth; i++)
        {
            if (lane.Kinds[i] is Ops.Xor or Ops.XorNot)
            {
                xors.Add(i);
            }
        }

        var seen = new HashSet<string>();
        for (var mask = 0; mask < 1 << xors.Count; mask++)
        {
            var kinds = (int[])lane.Kinds.Clone();
            var ks = (int[])lane.Ks.Clone();
            for (var bit = 0; bit < xors.Count; bit++)
            {
                if ((mask & (1 << bit)) != 0)
                {
                    kinds[xors[bit]] = kinds[xors[bit]] == Ops.Xor ? Ops.XorNot : Ops.Xor;
                }
            }

            for (var insert = -1; insert <= kinds.Length; insert++)
            {
                var candidate = insert < 0
                    ? new Candidate(kinds, ks, 0)
                    : new Candidate(
                        [.. kinds[..insert], Ops.Not, .. kinds[insert..]],
                        [.. ks[..insert], 0, .. ks[insert..]],
                        0);
                if (seen.Add(candidate.Describe()))
                {
                    yield return candidate;
                }
            }
        }
    }

    /// <summary>
    /// A 32-bit lane in its own terms. <c>Candidate.Describe</c> names the
    /// 64-bit operations, which would print `swap64` for an operation on a
    /// 32-bit value and `ror` for an operand that is a rotate *left*.
    /// </summary>
    public static string Describe(Candidate variant)
    {
        var parts = new List<string>();
        for (var i = 0; i < variant.Depth; i++)
        {
            var k = Math.Max(variant.Ks[i], 1);
            parts.Add(variant.Kinds[i] switch
            {
                Ops.Swap => "swap32",
                Ops.Reverse => "reverse32",
                Ops.Sbox => "sbox32",
                Ops.Not => "not",
                Ops.Add => $"add rol{k}",
                Ops.Sub => $"sub rol{k}",
                Ops.Xor => $"xor rol{k}",
                Ops.XorNot => $"xor ~rol{k}",
                Ops.RotR => $"rotr32 by (rol{k} % 31) + 1",
                Ops.RotL => $"rotl32 by (rol{k} % 31) + 1",
                _ => throw new ArgumentOutOfRangeException(nameof(variant)),
            });
        }

        return string.Join(" -> ", parts);
    }

    public static int Score(Candidate variant, Lane lane, BuildConstants constants, IReadOnlyList<Tail32> payloads)
    {
        var lane32 = new Lane32(variant);
        var buffer = new byte[(SeedCorpus.MaxBits / 8) + 4];
        var ok = 0;

        foreach (var payload in payloads)
        {
            var mixed = Keystream.Mixed(
                payload.Seed, constants.SeedAddend, constants.InitAOffset, constants.InitAAdds);
            var states = Keystream.States(payload.Seed, mixed, payload.Blocks + 1);
            for (var block = 0; block < payload.Blocks; block++)
            {
                BitConverter.TryWriteBytes(
                    buffer.AsSpan(block * 8, 8),
                    lane.Apply(BitConverter.ToUInt64(payload.Data, block * 8), states[block]));
            }

            BitConverter.TryWriteBytes(
                buffer.AsSpan(payload.Blocks * 8, 4),
                lane32.Apply(BitConverter.ToUInt32(payload.Data, payload.Blocks * 8), states[payload.Blocks]));

            if (Chain.Consumes(buffer.AsSpan(0, payload.Bits / 8), payload.Bits))
            {
                ok++;
            }
        }

        return ok;
    }
}

/// <summary>Riot's 32-bit substitution table, and the check that it is one.</summary>
public static class Tables
{
    // Copied from libraries/vrfnet/payload_transform.py, which asserts the
    // permutation property -- a truncated table is still valid hex and would
    // fail silently, far from here.
    private const string Substitute32Hex =
        "2167B396313FBAD3D5062B16F1B651A79C7B419584251536A4703546B05FA6C3" +
        "BB8638F62EA2A994831B6239F3D228149E9AF2C9DECC26A1D8D0748D69127189" +
        "F758CD4DB7114809B968C77CF42042F56B54756DA81D6A07D7C50EA066DB" +
        "F899AD1004FF8FB1EF986C29E201183D371E654B4A6E24D9BD90FE135693" +
        "34AA8B0D79E74992F98ECA43CBC6DA022D8C0FB2C08A4785AEE0D477C40B" +
        "5C617E335745E62FFD6F915B9FCF3C4FE33AEDE480087372EA63FBFCB8" +
        "7A23A51F815952875DFA78C1B5BEB4A3641C3253F07FDC3B7640EC309755" +
        "4C00BC880C05E1DF197D22C25A9BE52A50BF1AC8035E2CD1ABDD44EE82" +
        "CE27AFEBD64E0AE9173E9DE8AC60";

    public static readonly byte[] Substitute32 = Convert.FromHexString(Substitute32Hex);

    // Riot's 8-bit substitution table, copied the same way.
    private const string Substitute8Hex =
        "0A6C6996CADC5A08B38339A0F9ADF4560E6E4C85649982D4885C8736239A112D" +
        "B8C4341866136F59E07422FAA665E2D7954E94B0779E1AEEE705A2C830900D9B" +
        "D219C93A471512A9291F53ACAF4352AEF54DBFBEE34A06D5D0A378A7D61C7A6B" +
        "81D8DEE568FB267EBCBAE8CCE4727F2CFCF0EC28716048EF3E038F1EF16A8DF2" +
        "461B9C86F7B476628A10FD6D0B3F9F2F555FC3C6921627D344840FE1808CB773" +
        "8945DB332550EA0414C50C32415E79A41D3D5B4037C1CFFE2B54EB9D4991F307" +
        "173CDA578BCD61F6CE702EFF2193972A7D67ABB57C5D0042A5D92051EDDD0209" +
        "C2D1F8BDBBE93524985838AAB9A8B27501CBC063DF3B8EC731B1A1B6E67B4B4F";

    public static readonly byte[] Substitute8 = Convert.FromHexString(Substitute8Hex);
}

/// <summary>
/// Whether a run of decoded bytes is a UE rep layout that consumes every one of
/// its bits, over a buffer that is already decoded.
///
/// <see cref="ExactChain"/> asks the same question of a payload it decodes
/// lazily, which is what a 2^32 sweep needs; this asks it of a payload that is
/// already whole, which is what a lane search needs, and neither is worth
/// bending into the other.
/// </summary>
public static class Chain
{
    public static bool Consumes(ReadOnlySpan<byte> data, int bits)
    {
        var pos = 1;
        var previousHandle = 0u;

        while (true)
        {
            if (!TryReadPacked(data, bits, ref pos, out var handle))
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

            if (!TryReadPacked(data, bits, ref pos, out var fieldBits))
            {
                return false;
            }

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

    private static bool TryReadPacked(ReadOnlySpan<byte> data, int bits, ref int pos, out uint value)
    {
        value = 0;
        var shift = 0;
        while (true)
        {
            if (pos + 8 > bits || shift >= 32)
            {
                return false;
            }

            var index = pos >> 3;
            var offset = pos & 7;
            uint group = data[index];
            if (offset != 0)
            {
                group = ((group >> offset) | ((uint)data[index + 1] << (8 - offset))) & 0xFF;
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
}
