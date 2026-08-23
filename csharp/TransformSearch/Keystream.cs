using System.Numerics;

namespace TransformSearch;

/// <summary>
/// The keystream a payload transform runs on, and the one unknown in it.
///
/// <c>apply</c> keys the first 64-bit block on <c>state = seed</c>, which is
/// plaintext in the bunch header -- that is what makes recovering the 64-bit
/// lane a problem in its own right. Every block after the first is keyed by a
/// state this class produces, and those depend on <c>prng_a</c>, hence on the
/// build's four constants.
///
/// The reduction that makes them recoverable: <c>prng_a</c> is
/// <c>mixed * MULTIPLIER</c> with <c>mixed</c> a 32-bit value, and
/// <c>prng_b</c> depends on the seed alone. So one 2^32 sweep over
/// <c>mixed</c>, for one seed, produces every state that seed's payloads use.
/// It is a search over a keystream rather than over four constants, and the
/// constants fall out of two solved seeds algebraically afterwards.
/// </summary>
public static class Keystream
{
    public const ulong Multiplier = 0x2545F4914F6CDD1DUL;

    /// <summary>
    /// <c>prng_b</c>'s initial value, which needs no constants at all.
    /// Ported from <c>payload_transform._initial_prng_b</c>.
    /// </summary>
    public static ulong InitialPrngB(uint seed)
    {
        var mixed = (((seed >> 15) ^ seed) >> 12) ^ (seed << 25) ^ seed;
        return mixed * Multiplier;
    }

    /// <summary>
    /// One step of the generator. The state handed in is not read: the next
    /// state is the high half of <c>prng_b + prng_a</c> and nothing else, which
    /// is precisely why a single sweep over <c>mixed</c> pins the whole chain.
    /// </summary>
    public static uint Advance(ref ulong prngA, ref ulong prngB)
    {
        var total = prngB + prngA;
        prngB ^= prngA;
        prngA = BitOperations.RotateRight(prngA, 9) ^ (prngB << 14) ^ prngB;
        prngB = BitOperations.RotateLeft(prngB, 36);
        return (uint)(total >> 32);
    }

    /// <summary>
    /// The states keying blocks 1..<paramref name="count"/>, the first being
    /// the seed itself.
    /// </summary>
    public static uint[] States(uint seed, uint mixed, int count)
    {
        var prngA = mixed * Multiplier;
        var prngB = InitialPrngB(seed);
        var states = new uint[count];
        if (count > 0)
        {
            states[0] = seed;
        }

        for (var i = 1; i < count; i++)
        {
            states[i] = Advance(ref prngA, ref prngB);
        }

        return states;
    }

    /// <summary>
    /// <c>mixed</c> as <c>_initial_prng_a</c> computes it, for a build whose
    /// constants are published. This is what a sweep is checked against.
    /// </summary>
    public static uint Mixed(uint seed, uint seedAddend, uint initAOffset, bool initAAdds)
    {
        var seedPlus = seed + seedAddend;
        var offset = initAAdds ? seed + initAOffset : seed - initAOffset;
        return (((seedPlus >> 15) ^ seedPlus) >> 12) ^ (offset * 0x02000000u) ^ seedPlus;
    }

    /// <summary>
    /// The inverse of <c>x -> (((x &gt;&gt; 15) ^ x) &gt;&gt; 12) ^ x</c>.
    ///
    /// Each fixed-point iteration settles twelve more high bits, because the
    /// shifted term only ever depends on bits above the ones it lands on, so
    /// three passes are enough for 32 bits and the fourth is a free check.
    /// </summary>
    public static uint Unmix(uint y)
    {
        var x = y;
        for (var i = 0; i < 4; i++)
        {
            x = y ^ ((((x >> 15) ^ x) >> 12));
        }

        return x;
    }
}

/// <summary>
/// One build's 64-bit lane, applied to a single value.
///
/// <see cref="Search"/> applies a composition across a whole corpus one
/// operation at a time, which is what makes the search fast; this applies a
/// whole composition to one value, which is what a keystream sweep needs. The
/// two must agree, and <c>constants --expect</c> is what proves they do.
/// </summary>
public sealed class Lane
{
    private readonly int[] kinds;
    private readonly int[] ks;

    public Lane(Candidate candidate)
    {
        kinds = candidate.Kinds;
        ks = candidate.Ks;
    }

    public ulong Apply(ulong value, uint state)
    {
        for (var d = 0; d < kinds.Length; d++)
        {
            var k = Math.Max(ks[d], 1);
            var ror = (ulong)Ops.RotR32(state, k);
            value = kinds[d] switch
            {
                Ops.Swap => Ops.Swap64(value),
                Ops.Reverse => Ops.Reverse64(value),
                Ops.Sbox => Ops.Sbox64(value),
                Ops.Not => ~value,
                Ops.Add => value + ror,
                Ops.Sub => value - ror,
                Ops.Xor => value ^ ror,
                Ops.XorNot => value ^ ~ror,
                Ops.RotR => BitOperations.RotateRight(value, (int)((ror % 63) + 1)),
                Ops.RotL => BitOperations.RotateLeft(value, (int)((ror % 63) + 1)),
                _ => throw new ArgumentOutOfRangeException(nameof(state)),
            };
        }

        return value;
    }
}
