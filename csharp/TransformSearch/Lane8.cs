using System.Text.Json;

namespace TransformSearch;

/// <summary>
/// One payload's worth of evidence about the 8-bit lane: the ciphertext byte,
/// the state that keys it, and the single plaintext byte the rep layout admits.
/// </summary>
public sealed record ByteCase(byte Cipher, uint State, byte Plain);

/// <summary>
/// The 8-bit lane, which is the one the 64-bit skeleton does not give away.
///
/// The other two lanes are a neighbourhood of the 64-bit one; this one carries
/// arbitrary multipliers -- 0x31, 0x29, 0x533, 0x0CC6DB61 and the rest -- so its
/// operands have to be found rather than derived. What it does share is the
/// skeleton: the same operation order, with a multiplier where the 64-bit lane
/// has a rotation.
///
/// Three facts make that searchable rather than hopeless:
///
/// * a chain of multipliers is one multiplier, because
///   <c>(state * a) * b == state * (a * b)</c>, so the mixes 13.01 and 13.02
///   build in two steps are a single value here;
/// * an operand masked to a byte depends on its multiplier only **modulo 256**,
///   which is 256 candidates rather than 2^32 -- only a rotate distance, which
///   takes <c>product % 7</c>, needs the whole 32-bit multiplier;
/// * a run of adds or subs is one slot however many the 64-bit lane has, since
///   <c>v + a + b</c> is <c>v + (a + b)</c> and the sum of two byte operands is
///   itself one. 12.11 shows this from the other side: its 64-bit lane
///   subtracts three operands where its 8-bit lane adds one.
///
/// And the last byte slot is not searched at all. Running a case forward through
/// the slots before it and backward through the operations after it leaves the
/// operand between them as arithmetic, and a case whose state is odd names its
/// multiplier outright.
/// </summary>
public static class Lane8Search
{
    /// <summary>
    /// Every multiplier a published 8-bit lane uses. It is a prior read off five
    /// builds rather than a fact about a sixth, and it only bounds the rotate
    /// slots: the byte slots are searched over all 256 residues.
    /// </summary>
    public static readonly uint[] RotateMultipliers =
        [0x0B, 0x1B, 0x23, 0x29, 0x31, 0x33, 0x79, 0x533, 0x2751B, 0x0CC6DB61];

    private static readonly byte[] Inverse8 = BuildInverse();

    private static byte[] BuildInverse()
    {
        var inverse = new byte[256];
        for (var i = 0; i < 256; i++)
        {
            inverse[Tables.Substitute8[i]] = (byte)i;
        }

        return inverse;
    }

    public static bool IsByteOp(int kind) => kind is Ops.Add or Ops.Sub or Ops.Xor or Ops.XorNot;

    public static bool IsRotateOp(int kind) => kind is Ops.RotR or Ops.RotL;

    /// <summary>
    /// The payloads that pin a plaintext byte: a whole number of 64-bit blocks
    /// and exactly one 8-bit block, where only one of the 256 possible last
    /// bytes lets the rep layout consume the payload.
    ///
    /// The 32-bit lane never runs on these -- it needs more than 31 bits left --
    /// and neither does the tail XOR, which needs a partial byte. So the 8-bit
    /// lane is the only unknown, and a wrong one has one chance in 256.
    /// </summary>
    public static List<ByteCase> Cases(
        string path,
        Lane lane,
        BuildConstants constants,
        int want)
    {
        var seen = new HashSet<string>();
        var cases = new List<ByteCase>();
        var buffer = new byte[(SeedCorpus.MaxBits / 8) + 1];

        foreach (var line in File.ReadLines(path))
        {
            if (line.Length == 0 || cases.Count >= want)
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            var bits = root.GetProperty("b").GetInt32();
            if (bits % 64 != 8 || bits < 72 || bits > SeedCorpus.MaxBits)
            {
                continue;
            }

            var seed = root.GetProperty("s").GetUInt32();
            var hex = root.GetProperty("p").GetString()![..(bits / 4)];
            if (!seen.Add($"{seed}:{hex}"))
            {
                continue;
            }

            var data = Convert.FromHexString(hex);
            var blocks = bits / 64;
            var mixed = Keystream.Mixed(seed, constants.SeedAddend, constants.InitAOffset, constants.InitAAdds);
            var states = Keystream.States(seed, mixed, blocks + 1);
            for (var block = 0; block < blocks; block++)
            {
                BitConverter.TryWriteBytes(
                    buffer.AsSpan(block * 8, 8),
                    lane.Apply(BitConverter.ToUInt64(data, block * 8), states[block]));
            }

            var accepted = -1;
            for (var candidate = 0; candidate < 256; candidate++)
            {
                buffer[blocks * 8] = (byte)candidate;
                if (!Chain.Consumes(buffer.AsSpan(0, (blocks * 8) + 1), bits))
                {
                    continue;
                }

                if (accepted >= 0)
                {
                    accepted = -1;
                    break;
                }

                accepted = candidate;
            }

            if (accepted >= 0)
            {
                cases.Add(new ByteCase(data[blocks * 8], states[blocks], (byte)accepted));
            }
        }

        return cases;
    }

    /// <summary>
    /// The op orders to try: the 64-bit skeleton's complement variants, with
    /// runs of adds and subs folded into one slot.
    /// </summary>
    public static List<int[]> Shapes(Candidate lane)
    {
        var shapes = new List<int[]>();
        var seen = new HashSet<string>();

        foreach (var variant in Lane32Search.Variants(lane))
        {
            var folded = new List<int>();
            foreach (var kind in variant.Kinds)
            {
                if (folded.Count > 0
                    && kind is Ops.Add or Ops.Sub
                    && folded[^1] is Ops.Add or Ops.Sub)
                {
                    continue;
                }

                folded.Add(kind);
            }

            var key = string.Join(",", folded);
            if (seen.Add(key))
            {
                shapes.Add([.. folded]);
            }
        }

        return shapes;
    }

    public static byte Apply(int[] shape, uint[] rotate, byte[] bytes, byte value, uint state)
    {
        int rot = 0, slot = 0;
        foreach (var kind in shape)
        {
            if (IsRotateOp(kind))
            {
                var product = state * rotate[rot];
                rot++;
                value = Step(kind, value, (byte)((product % 7) + 1));
            }
            else if (IsByteOp(kind))
            {
                value = Step(kind, value, (byte)(state * bytes[slot]));
                slot++;
            }
            else
            {
                value = Step(kind, value, 0);
            }
        }

        return value;
    }

    private static byte Step(int kind, byte value, byte operand) => kind switch
    {
        Ops.Swap => (byte)(((value & 0x55) << 1) | ((value >> 1) & 0x55)),
        Ops.Reverse => Reverse8(value),
        Ops.Sbox => Tables.Substitute8[value],
        Ops.Not => (byte)~value,
        Ops.Add => (byte)(value + operand),
        Ops.Sub => (byte)(value - operand),
        Ops.Xor => (byte)(value ^ operand),
        Ops.XorNot => (byte)(value ^ (byte)~operand),
        Ops.RotR => (byte)((value >> operand) | (value << (8 - operand))),
        Ops.RotL => (byte)((value << operand) | (value >> (8 - operand))),
        _ => throw new ArgumentOutOfRangeException(nameof(kind)),
    };

    private static byte Undo(int kind, byte value, byte operand) => kind switch
    {
        Ops.Swap => Step(Ops.Swap, value, 0),
        Ops.Reverse => Reverse8(value),
        Ops.Sbox => Inverse8[value],
        Ops.Not => (byte)~value,
        Ops.Add => (byte)(value - operand),
        Ops.Sub => (byte)(value + operand),
        Ops.Xor => (byte)(value ^ operand),
        Ops.XorNot => (byte)(value ^ (byte)~operand),
        Ops.RotR => Step(Ops.RotL, value, operand),
        Ops.RotL => Step(Ops.RotR, value, operand),
        _ => throw new ArgumentOutOfRangeException(nameof(kind)),
    };

    private static byte Reverse8(byte v)
    {
        v = (byte)(((v & 0x55) << 1) | ((v >> 1) & 0x55));
        v = (byte)(((v & 0x33) << 2) | ((v >> 2) & 0x33));
        return (byte)((v << 4) | (v >> 4));
    }

    /// <summary>
    /// The byte the final byte slot must contribute, for one case, given
    /// everything before it.
    /// </summary>
    private static byte Required(int[] shape, int last, uint[] rotate, byte[] prefix, ByteCase probe)
    {
        int rot = 0, slot = 0;
        var value = probe.Cipher;
        for (var i = 0; i < last; i++)
        {
            var kind = shape[i];
            if (IsRotateOp(kind))
            {
                value = Step(kind, value, (byte)(((probe.State * rotate[rot]) % 7) + 1));
                rot++;
            }
            else if (IsByteOp(kind))
            {
                value = Step(kind, value, (byte)(probe.State * prefix[slot]));
                slot++;
            }
            else
            {
                value = Step(kind, value, 0);
            }
        }

        var tailRotate = rot;
        for (var i = last + 1; i < shape.Length; i++)
        {
            if (IsRotateOp(shape[i]))
            {
                tailRotate++;
            }
        }

        var after = probe.Plain;
        for (var i = shape.Length - 1; i > last; i--)
        {
            var kind = shape[i];
            if (IsRotateOp(kind))
            {
                tailRotate--;
                after = Undo(kind, after, (byte)(((probe.State * rotate[tailRotate]) % 7) + 1));
            }
            else
            {
                after = Undo(kind, after, 0);
            }
        }

        return shape[last] switch
        {
            Ops.Add => (byte)(after - value),
            Ops.Sub => (byte)(value - after),
            Ops.Xor => (byte)(value ^ after),
            Ops.XorNot => (byte)~(value ^ after),
            _ => throw new ArgumentOutOfRangeException(nameof(shape)),
        };
    }

    /// <summary>Multipliers M with <c>(state * M) &amp; 0xFF == wanted</c>.</summary>
    private static IEnumerable<byte> MultipliersFor(uint state, byte wanted)
    {
        for (var m = 0; m < 256; m++)
        {
            if ((byte)(state * (uint)m) == wanted)
            {
                yield return (byte)m;
            }
        }
    }

    public sealed record Fit(int[] Shape, uint[] Rotate, byte[] Bytes, int Held);

    /// <summary>
    /// Every 8-bit lane that reproduces the fitting cases, with how many of the
    /// held-out ones it also reproduces.
    ///
    /// A wrong lane has one chance in 256 per case, so six fitting cases are
    /// 2^48 against and the held-out column is what says so out loud.
    /// </summary>
    public static List<Fit> Run(
        List<int[]> shapes,
        IReadOnlyList<ByteCase> fit,
        IReadOnlyList<ByteCase> held,
        int degreeOfParallelism,
        int stop)
    {
        var found = new List<Fit>();

        Parallel.ForEach(
            shapes,
            new ParallelOptions { MaxDegreeOfParallelism = degreeOfParallelism },
            shape =>
            {
                var byteSlots = shape.Count(IsByteOp);
                var rotateSlots = shape.Count(IsRotateOp);
                if (byteSlots == 0)
                {
                    return;
                }

                var last = Array.FindLastIndex(shape, IsByteOp);
                var rotate = new uint[Math.Max(rotateSlots, 1)];
                var bytes = new byte[byteSlots];
                var prefix = new byte[byteSlots - 1];

                foreach (var rotation in Choices(RotateMultipliers, rotateSlots))
                {
                    Array.Copy(rotation, rotate, rotateSlots);
                    for (var combination = 0L; combination < 1L << (8 * prefix.Length); combination++)
                    {
                        for (var i = 0; i < prefix.Length; i++)
                        {
                            prefix[i] = (byte)(combination >> (8 * i));
                        }

                        var wanted = Required(shape, last, rotate, prefix, fit[0]);
                        foreach (var tail in MultipliersFor(fit[0].State, wanted))
                        {
                            Array.Copy(prefix, bytes, prefix.Length);
                            bytes[^1] = tail;

                            var fits = true;
                            foreach (var probe in fit)
                            {
                                if (Apply(shape, rotate, bytes, probe.Cipher, probe.State) != probe.Plain)
                                {
                                    fits = false;
                                    break;
                                }
                            }

                            if (!fits)
                            {
                                continue;
                            }

                            var agree = held.Count(p => Apply(shape, rotate, bytes, p.Cipher, p.State) == p.Plain);
                            lock (found)
                            {
                                found.Add(new Fit(shape, (uint[])rotate.Clone(), (byte[])bytes.Clone(), agree));

                                // Stop on an answer, never on a count. Six
                                // fitted cases are 2^48 against a wrong lane and
                                // still admit lanes that fit those six and no
                                // others -- 13.00 produces several before the
                                // published one, and returning after the first
                                // few would report them as the answer. What ends
                                // the search is a lane that also reproduces
                                // every held-out case.
                                if (agree == held.Count || found.Count >= stop)
                                {
                                    return;
                                }
                            }
                        }
                    }
                }
            });

        return found;
    }

    private static IEnumerable<uint[]> Choices(uint[] pool, int slots)
    {
        if (slots == 0)
        {
            yield return [];
            yield break;
        }

        var index = new int[slots];
        while (true)
        {
            yield return [.. index.Select(i => pool[i])];

            var position = slots - 1;
            while (position >= 0)
            {
                index[position]++;
                if (index[position] < pool.Length)
                {
                    break;
                }

                index[position] = 0;
                position--;
            }

            if (position < 0)
            {
                yield break;
            }
        }
    }

    public static string Describe(Fit fit)
    {
        var parts = new List<string>();
        int rot = 0, slot = 0;
        foreach (var kind in fit.Shape)
        {
            if (IsRotateOp(kind))
            {
                parts.Add($"{(kind == Ops.RotR ? "rotr8" : "rotl8")} by (state * 0x{fit.Rotate[rot]:X} % 7) + 1");
                rot++;
            }
            else if (IsByteOp(kind))
            {
                var name = kind switch
                {
                    Ops.Add => "add",
                    Ops.Sub => "sub",
                    Ops.Xor => "xor",
                    _ => "xor ~",
                };
                parts.Add($"{name} (state * 0x{fit.Bytes[slot]:X2}) & 0xFF");
                slot++;
            }
            else
            {
                parts.Add(kind switch
                {
                    Ops.Swap => "swap8",
                    Ops.Reverse => "reverse8",
                    Ops.Sbox => "sbox8",
                    _ => "not",
                });
            }
        }

        return string.Join(" -> ", parts);
    }
}
