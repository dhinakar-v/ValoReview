using System.Text.Json;

namespace TransformSearch;

/// <summary>
/// One payload's worth of evidence about the 8-bit lane: the ciphertext byte,
/// the state that keys it, and what the rep layout says the plaintext byte is.
///
/// <c>Mask</c> is which of those eight bits the layout actually pins. A payload
/// ending on a byte boundary pins all eight and always to zero; one ending
/// mid-byte pins seven and leaves the eighth free, and those are the cases that
/// carry any evidence about a rotate at all.
/// </summary>
public sealed record ByteCase(byte Cipher, uint State, byte Plain, byte Mask);

/// <summary>
/// An 8-bit lane that reproduces every fitted case: its operation order, its
/// byte multipliers, and how many held-out cases it reproduces as well.
///
/// It carries no rotate multipliers, because the search does not guess any --
/// it solves each case's rotate *distances*, which are seven values rather than
/// 2^32. The multiplier behind those distances is recovered afterwards, by
/// <see cref="Lane8Search.Recover"/>, and a lane whose distances no multiplier
/// explains is not a lane at all.
/// </summary>
public sealed record Fit(int[] Shape, byte[] Bytes, int Held);

/// <summary>
/// What a fit's rotate slots turned out to be: one multiplier per slot for each
/// way the cases can be explained, and whether a slot's scan was abandoned for
/// want of constraint -- which is a different answer from "nothing fits" and
/// must not be read as one.
/// </summary>
public sealed record Recovery(List<uint[]> Multipliers, bool Underconstrained);

/// <summary>
/// The 8-bit lane, which is the one the 64-bit skeleton does not give away.
///
/// The other two lanes are a neighbourhood of the 64-bit one; this one carries
/// arbitrary multipliers -- 0x31, 0x29, 0x533, 0x0CC6DB61 and the rest -- so its
/// operands have to be found rather than derived. What it does share is the
/// skeleton: the same operation order, with a multiplier where the 64-bit lane
/// has a rotation.
///
/// Four facts make that searchable rather than hopeless:
///
/// * a chain of multipliers is one multiplier, because
///   <c>(state * a) * b == state * (a * b)</c>, so the mixes 13.01 and 13.02
///   build in two steps are a single value here;
/// * an operand masked to a byte depends on its multiplier only **modulo 256**,
///   which is 256 candidates rather than 2^32;
/// * a rotate slot's multiplier is not searched at all. A distance is
///   <c>(product % 7) + 1</c>, so a case admits seven of them per slot whatever
///   the multiplier is, and fitting the distances per case assumes nothing about
///   the multiplier that produced them. The multiplier is then one 2^32 scan per
///   slot, which the first case cuts by seven eighths;
/// * a run of adds or subs is one slot however many the 64-bit lane has, since
///   <c>v + a + b</c> is <c>v + (a + b)</c> and the sum of two byte operands is
///   itself one. 12.11 shows this from the other side: its 64-bit lane
///   subtracts three operands where its 8-bit lane adds one.
///
/// And the last byte slot is not searched either. Running a case forward through
/// the slots before it and backward through the operations after it leaves the
/// operand between them as arithmetic, and a case whose state is odd names its
/// multiplier outright.
/// </summary>
public static class Lane8Search
{
    /// <summary>Rotate distances a byte lane can take: <c>(product % 7) + 1</c>.</summary>
    public const int DistanceCount = 7;

    /// <summary>
    /// Byte slots a shape may carry before it is refused. Every slot but the
    /// last is enumerated over 256 residues, so a fifth one is 2^32 candidates
    /// per shape and would run for hours without saying why.
    /// </summary>
    public const int MaxByteSlots = 4;

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
    /// Plaintext bits a payload must pin before it is worth keeping. Seven of
    /// eight is one chance in 128 for a wrong lane, and it is what the payloads
    /// that pin a rotate distance actually offer.
    /// </summary>
    public const int MinPinnedBits = 7;

    /// <summary>
    /// The payloads that pin their last lane byte: a whole number of 64-bit
    /// blocks, then exactly one 8-bit block, then at most seven bits of tail.
    ///
    /// The 32-bit lane never runs on these -- it needs more than 31 bits left --
    /// and the tail XOR needs no lane at all, only <c>tail_xor</c> and the
    /// keystream byte, both known once the constants are. So the 8-bit lane is
    /// the only unknown, and the rep layout is what says what it must produce:
    /// of the 256 possible bytes, few let the payload consume to exactly zero
    /// bits, and the bits every survivor agrees on are the case's evidence.
    ///
    /// **A payload whose bit count is a whole number of bytes pins its byte to
    /// <c>0x00</c> every single time, and that is measured rather than argued.**
    /// It is the chain's terminating zero handle, byte-aligned by construction,
    /// so all 39 such cases of 12.10 and all 27 of 13.00 carry the same
    /// plaintext -- and a lane whose last operation is a rotate then has *no*
    /// evidence about that rotate at all, because every distance rotates zero to
    /// zero. 13.00's final multiplier is not identifiable from those payloads,
    /// and the search says so rather than reporting whichever value it tried
    /// first.
    ///
    /// **What breaks that tie is the partial byte.** With a tail the terminator
    /// straddles a byte boundary, so the lane byte carries seven zeroes and one
    /// real bit: 2,443 payloads of the 13.00 corpus pin seven of eight bits
    /// where 27 pin all eight, and a case whose real bit is set pins a rotate
    /// distance outright. Hence <see cref="ByteCase.Mask"/>, and hence the two
    /// quotas -- a fitted case has to be fully pinned, because the final byte
    /// slot is *solved* from its plaintext rather than searched.
    /// </summary>
    public static List<ByteCase> Cases(
        string path,
        Lane lane,
        BuildConstants constants,
        int wantPinned,
        int wantMasked)
    {
        var seen = new HashSet<uint>();
        var pinned = new List<ByteCase>();
        var masked = new List<ByteCase>();
        var buffer = new byte[(SeedCorpus.MaxBits / 8) + 1];
        var accepted = new List<int>();

        foreach (var line in File.ReadLines(path))
        {
            if (line.Length == 0 || (pinned.Count >= wantPinned && masked.Count >= wantMasked))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            var bits = root.GetProperty("b").GetInt32();
            if (bits < 72 || bits > SeedCorpus.MaxBits)
            {
                continue;
            }

            // What `apply` leaves after its 64-bit blocks: 8-bit blocks while
            // more than seven bits remain, then a tail XOR over the rest. Eight
            // to fifteen bits is one 8-bit block and nothing else -- sixteen
            // would be two, which is 65,536 chain parses for a payload kind that
            // pins nothing measurable, and thirty-two would reach the 32-bit
            // lane, whose answer this search must not depend on.
            var remaining = bits % 64;
            if (remaining is < 8 or > 15)
            {
                continue;
            }

            var seed = root.GetProperty("s").GetUInt32();
            var bytes = (bits + 7) / 8;
            var hex = root.GetProperty("p").GetString()![..(2 * bytes)];

            var data = Convert.FromHexString(hex);
            var blocks = bits / 64;
            var mixed = Keystream.Mixed(seed, constants.SeedAddend, constants.InitAOffset, constants.InitAAdds);
            var states = Keystream.States(seed, mixed, blocks + 2);
            for (var block = 0; block < blocks; block++)
            {
                BitConverter.TryWriteBytes(
                    buffer.AsSpan(block * 8, 8),
                    lane.Apply(BitConverter.ToUInt64(data, block * 8), states[block]));
            }

            if (remaining > 8)
            {
                var tail = (byte)(0xFF >> (7 - ((bits - 1) & 7)));
                var stream = (byte)(states[blocks + 1] ^ constants.TailXor);
                buffer[bytes - 1] = (byte)((data[bytes - 1] ^ stream) & tail);
            }

            accepted.Clear();
            for (var candidate = 0; candidate < 256; candidate++)
            {
                buffer[blocks * 8] = (byte)candidate;
                if (Chain.Consumes(buffer.AsSpan(0, bytes), bits))
                {
                    accepted.Add(candidate);
                }
            }

            if (accepted.Count == 0)
            {
                continue;
            }

            var mask = 0xFF;
            foreach (var candidate in accepted)
            {
                mask &= ~(candidate ^ accepted[0]);
            }

            if (System.Numerics.BitOperations.PopCount((uint)(mask & 0xFF)) < MinPinnedBits)
            {
                continue;
            }

            // One state, one case. Two payloads keyed by the same state say the
            // same thing to a multiplier scan -- the distance it implies is the
            // same -- so a corpus full of repeats reads as evidence it is not,
            // and 13.00's 212 cases turn out to carry 26 distinct states.
            if (!seen.Add(states[blocks]))
            {
                continue;
            }

            var probe = new ByteCase(
                data[blocks * 8], states[blocks], (byte)(accepted[0] & mask), (byte)mask);
            var into = mask == 0xFF ? pinned : masked;
            if (into.Count < (mask == 0xFF ? wantPinned : wantMasked))
            {
                into.Add(probe);
            }
        }

        return [.. pinned, .. masked];
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

                // A `not` between two adds is a `not` in front of them:
                // ~(v + a) + b is ~v + (b - a), and the difference of two byte
                // operands is a byte operand. Moving it there lets the pair fold
                // like any other run -- which matters, because a shape that
                // keeps them apart carries a fourth byte slot and costs 256
                // times as much to search for a function already covered here.
                if (folded.Count >= 2
                    && kind is Ops.Add or Ops.Sub
                    && folded[^1] == Ops.Not
                    && folded[^2] is Ops.Add or Ops.Sub)
                {
                    folded.RemoveAt(folded.Count - 1);
                    folded.Insert(folded.Count - 1, Ops.Not);
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

    /// <summary>Whether a shape is inside <see cref="MaxByteSlots"/>.</summary>
    public static bool Searchable(int[] shape) => shape.Count(IsByteOp) is > 0 and <= MaxByteSlots;

    /// <summary>
    /// Every rotate-distance vector a shape's rotate slots can take, in base
    /// seven. Two slots is 49 vectors, which is what makes solving the
    /// distances cheaper than guessing the multipliers behind them.
    /// </summary>
    public static byte[][] Vectors(int slots)
    {
        var total = 1;
        for (var slot = 0; slot < slots; slot++)
        {
            total *= DistanceCount;
        }

        var vectors = new byte[total][];
        for (var index = 0; index < total; index++)
        {
            var vector = new byte[slots];
            var rest = index;
            for (var slot = 0; slot < slots; slot++)
            {
                vector[slot] = (byte)((rest % DistanceCount) + 1);
                rest /= DistanceCount;
            }

            vectors[index] = vector;
        }

        return vectors;
    }

    public static byte Apply(int[] shape, byte[] distances, byte[] bytes, byte value, uint state)
    {
        int rot = 0, slot = 0;
        foreach (var kind in shape)
        {
            if (IsRotateOp(kind))
            {
                value = Step(kind, value, distances[rot]);
                rot++;
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
    private static byte Required(int[] shape, int last, byte[] distances, byte[] prefix, ByteCase probe)
    {
        int rot = 0, slot = 0;
        var value = probe.Cipher;
        for (var i = 0; i < last; i++)
        {
            var kind = shape[i];
            if (IsRotateOp(kind))
            {
                value = Step(kind, value, distances[rot]);
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
                after = Undo(kind, after, distances[tailRotate]);
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

    /// <summary>
    /// For one state, the byte multipliers producing each possible operand.
    /// An odd state names one multiplier per operand; an even one names several
    /// and leaves the rest unreachable.
    /// </summary>
    private static byte[][] TailTable(uint state)
    {
        var lists = new List<byte>[256];
        for (var operand = 0; operand < 256; operand++)
        {
            lists[operand] = [];
        }

        for (var multiplier = 0; multiplier < 256; multiplier++)
        {
            lists[(byte)(state * (uint)multiplier)].Add((byte)multiplier);
        }

        return [.. lists.Select(list => list.ToArray())];
    }

    /// <summary>
    /// How many cases a fully recovered lane reproduces -- multipliers and all,
    /// so the distances are determined rather than chosen per case.
    ///
    /// This is the form to score a lane on a corpus the search never saw, and it
    /// is a stricter question than the one the search asks: there, a case may
    /// pick whichever distance suits it.
    /// </summary>
    public static int Holds(int[] shape, byte[] bytes, uint[] rotate, IReadOnlyList<ByteCase> cases)
    {
        var distances = new byte[Math.Max(rotate.Length, 1)];
        var held = 0;
        foreach (var probe in cases)
        {
            for (var slot = 0; slot < rotate.Length; slot++)
            {
                distances[slot] = (byte)(((probe.State * rotate[slot]) % DistanceCount) + 1);
            }

            if (((Apply(shape, distances, bytes, probe.Cipher, probe.State) ^ probe.Plain) & probe.Mask) == 0)
            {
                held++;
            }
        }

        return held;
    }

    /// <summary>Whether some distance vector reproduces this case's plaintext byte.</summary>
    private static bool Fits(int[] shape, byte[][] vectors, byte[] bytes, ByteCase probe)
    {
        foreach (var vector in vectors)
        {
            if (((Apply(shape, vector, bytes, probe.Cipher, probe.State) ^ probe.Plain) & probe.Mask) == 0)
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Every set of byte multipliers that reproduces the fitting cases under
    /// some rotate distance per case, with how many of the held-out ones it
    /// reproduces too.
    ///
    /// A wrong lane fits a case for one distance vector in 256, so with two
    /// rotate slots it clears one case in six and six fitted cases are about
    /// 2^13 against -- weaker per case than a fixed-multiplier search, which is
    /// why the held-out column and the multiplier recovery both matter and
    /// neither is optional.
    /// </summary>
    public static List<Fit> Run(
        List<int[]> shapes,
        IReadOnlyList<ByteCase> fit,
        IReadOnlyList<ByteCase> held,
        int degreeOfParallelism,
        int stop)
    {
        var found = new List<Fit>();
        var tails = TailTable(fit[0].State);

        Parallel.ForEach(
            shapes.Where(Searchable),
            new ParallelOptions { MaxDegreeOfParallelism = degreeOfParallelism },
            shape =>
            {
                var vectors = Vectors(shape.Count(IsRotateOp));
                var last = Array.FindLastIndex(shape, IsByteOp);
                var bytes = new byte[shape.Count(IsByteOp)];
                var prefix = new byte[bytes.Length - 1];

                // The same byte multipliers arrive under many distance vectors,
                // and what a candidate is judged on is the multipliers alone --
                // the distances are free per case. Testing one twice would cost
                // the search a factor of the vector count. The bitmap is one bit
                // per multiplier tuple, which is 2 MB at three slots and is why
                // a fourth slot goes without.
                var seen = bytes.Length < MaxByteSlots ? new byte[1 << ((8 * bytes.Length) - 3)] : null;

                foreach (var vector in vectors)
                {
                    for (var combination = 0; combination < 1 << (8 * prefix.Length); combination++)
                    {
                        for (var i = 0; i < prefix.Length; i++)
                        {
                            prefix[i] = (byte)(combination >> (8 * i));
                        }

                        var wanted = Required(shape, last, vector, prefix, fit[0]);
                        foreach (var tail in tails[wanted])
                        {
                            if (seen is not null)
                            {
                                var tuple = combination | (tail << (8 * prefix.Length));
                                var bit = (byte)(1 << (tuple & 7));
                                if ((seen[tuple >> 3] & bit) != 0)
                                {
                                    continue;
                                }

                                seen[tuple >> 3] |= bit;
                            }

                            Array.Copy(prefix, bytes, prefix.Length);
                            bytes[^1] = tail;

                            var fits = true;
                            for (var i = 1; i < fit.Count && fits; i++)
                            {
                                fits = Fits(shape, vectors, bytes, fit[i]);
                            }

                            if (!fits)
                            {
                                continue;
                            }

                            var agree = held.Count(probe => Fits(shape, vectors, bytes, probe));
                            lock (found)
                            {
                                found.Add(new Fit(shape, (byte[])bytes.Clone(), agree));
                                if (found.Count >= stop)
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

    /// <summary>
    /// The rotate multipliers behind a fit's per-case distances, or nothing if
    /// no multiplier explains them.
    ///
    /// This is the second half of the search and it is a filter as much as a
    /// recovery: the fitting stage lets every case pick its own distance, so a
    /// surviving lane still has to show that one 32-bit multiplier per slot
    /// produces the distance every case needed. A slot is a 2^32 scan whose
    /// first case rejects six candidates in seven, and with a few dozen cases a
    /// wrong lane has nothing left.
    /// </summary>
    public static Recovery Recover(
        int[] shape,
        byte[] bytes,
        IReadOnlyList<ByteCase> cases,
        int degreeOfParallelism,
        int cap)
    {
        var slots = shape.Count(IsRotateOp);
        var vectors = Vectors(slots);
        var allowed = new List<int>[cases.Count];
        for (var i = 0; i < cases.Count; i++)
        {
            allowed[i] = [];
            for (var v = 0; v < vectors.Length; v++)
            {
                var produced = Apply(shape, vectors[v], bytes, cases[i].Cipher, cases[i].State);
                if (((produced ^ cases[i].Plain) & cases[i].Mask) == 0)
                {
                    allowed[i].Add(v);
                }
            }

            if (allowed[i].Count == 0)
            {
                return new Recovery([], false);
            }
        }

        var run = new Recovering(
            vectors, [.. cases.Select(probe => probe.State)], slots, Math.Max(degreeOfParallelism, 1), cap);
        run.Fix(0, allowed, new uint[slots]);
        return new Recovery(run.Results, run.Underconstrained);
    }

    /// <summary>
    /// One slot at a time: scan for the multipliers whose distances every case
    /// can live with, fix one, and let the slots after it see only the vectors
    /// that survive it.
    /// </summary>
    private sealed class Recovering(byte[][] vectors, uint[] states, int slots, int workers, int cap)
    {
        /// <summary>
        /// Multipliers kept per slot before a scan is abandoned. A scan that
        /// reaches it means the cases do not constrain the slot, which is a
        /// different answer from "none fits" and is reported as one.
        /// </summary>
        private const int ScanCap = 1024;

        public List<uint[]> Results { get; } = [];

        public bool Underconstrained { get; private set; }

        public void Fix(int slot, List<int>[] allowed, uint[] chosen)
        {
            if (slot == slots)
            {
                Results.Add((uint[])chosen.Clone());
                return;
            }

            var masks = new byte[states.Length];
            for (var i = 0; i < states.Length; i++)
            {
                foreach (var v in allowed[i])
                {
                    masks[i] |= (byte)(1 << (vectors[v][slot] - 1));
                }
            }

            // What a scan would keep, before running it: a multiplier clears a
            // case with probability popcount(mask) / 7, so a slot whose cases
            // admit most distances has more survivors than the cap and the scan
            // has nothing to say. Reporting that costs nothing; discovering it
            // by scanning 2^32 costs seconds per candidate lane.
            var expected = (double)uint.MaxValue;
            foreach (var mask in masks)
            {
                expected *= System.Numerics.BitOperations.PopCount(mask) / (double)DistanceCount;
            }

            if (expected > ScanCap)
            {
                Underconstrained = true;
                return;
            }

            // A case whose mask admits every distance says nothing about this
            // slot, and one that admits few says the most. Scanning them in that
            // order is what makes the 2^32 sweep an early-exit loop rather than
            // a walk over a thousand cases per candidate: 13.00 goes from 36
            // seconds a slot to under four.
            var order = Enumerable.Range(0, states.Length)
                .Where(i => System.Numerics.BitOperations.PopCount(masks[i]) < DistanceCount)
                .OrderBy(i => System.Numerics.BitOperations.PopCount(masks[i]))
                .ToArray();

            foreach (var multiplier in Scan([.. order.Select(i => states[i])], [.. order.Select(i => masks[i])]))
            {
                var next = new List<int>[states.Length];
                var ok = true;
                for (var i = 0; i < states.Length && ok; i++)
                {
                    var distance = (byte)(((states[i] * multiplier) % DistanceCount) + 1);
                    next[i] = [.. allowed[i].Where(v => vectors[v][slot] == distance)];
                    ok = next[i].Count > 0;
                }

                if (!ok)
                {
                    continue;
                }

                chosen[slot] = multiplier;
                Fix(slot + 1, next, chosen);
                if (Results.Count >= cap)
                {
                    return;
                }
            }
        }

        /// <summary>
        /// Every 32-bit multiplier whose <c>(state * M) % 7</c> lands inside
        /// each case's allowed set. The whole 2^32 is scanned because the
        /// published multipliers are a prior about five builds and the rotate
        /// slot is exactly where that prior turned out to be wrong.
        /// </summary>
        private List<uint> Scan(uint[] keys, byte[] masks)
        {
            var found = new List<uint>();

            Parallel.For(0, workers, worker =>
            {
                for (var value = (ulong)worker; value <= uint.MaxValue; value += (ulong)workers)
                {
                    var multiplier = (uint)value;
                    var ok = true;
                    for (var i = 0; i < keys.Length; i++)
                    {
                        if ((masks[i] & (1 << (int)((keys[i] * multiplier) % DistanceCount))) == 0)
                        {
                            ok = false;
                            break;
                        }
                    }

                    if (!ok)
                    {
                        continue;
                    }

                    lock (found)
                    {
                        found.Add(multiplier);
                        if (found.Count >= ScanCap)
                        {
                            return;
                        }
                    }
                }
            });

            if (found.Count >= ScanCap)
            {
                Underconstrained = true;
            }

            found.Sort();
            return found;
        }
    }

    public static string Describe(int[] shape, byte[] bytes, uint[]? rotate)
    {
        var parts = new List<string>();
        int rot = 0, slot = 0;
        foreach (var kind in shape)
        {
            if (IsRotateOp(kind))
            {
                var multiplier = rotate is null ? "?" : $"0x{rotate[rot]:X}";
                parts.Add($"{(kind == Ops.RotR ? "rotr8" : "rotl8")} by (state * {multiplier} % 7) + 1");
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
                parts.Add($"{name} (state * 0x{bytes[slot]:X2}) & 0xFF");
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
