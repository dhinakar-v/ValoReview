namespace TransformSearch;

/// <summary>
/// The operation vocabulary a Valorant 64-bit payload mixing function is built
/// from, and the primitives it is built out of.
///
/// The vocabulary is not a guess. Every published transform's <c>_u64</c> --
/// 12.10, 12.11, 13.00, 13.01, 13.02 -- is a composition of exactly these ten
/// kinds, and every state operand any of them uses is <c>rotr32(state, k)</c>
/// for k in 1..8. The arbitrary multipliers (0x533, 0x79, 0x0CC6DB61) that
/// appear in those builds belong to the 8-bit lane and never to this one.
/// </summary>
public static class Ops
{
    public const int Swap = 0;
    public const int Reverse = 1;
    public const int Sbox = 2;
    public const int Not = 3;
    public const int Add = 4;
    public const int Sub = 5;
    public const int Xor = 6;
    public const int XorNot = 7;
    public const int RotR = 8;
    public const int RotL = 9;

    /// <summary>Kinds at or above this index carry a <c>rotr32(state, k)</c> operand.</summary>
    public const int FirstOperandKind = Add;
    public const int KindCount = 10;

    /// <summary>The largest k any published transform's 64-bit lane uses.</summary>
    public const int MaxK = 8;

    /// <summary>
    /// The largest k the per-payload operand tables hold, which is every
    /// rotation a 32-bit state has.
    ///
    /// It is wider than <see cref="MaxK"/> on purpose. The 32-bit lane of every
    /// published build draws its operands from <c>rotl32(state, k)</c> where
    /// the 64-bit lane uses <c>rotr32(state, k)</c>, and a left rotation by k
    /// is a right rotation by 32 - k. So a build whose 64-bit lane reaches for
    /// the left-handed operand is asking for k in 24..31, and a search bounded
    /// at 8 cannot express it at all.
    /// </summary>
    public const int Stride = 31;

    public static string Name(int kind, int k) => kind switch
    {
        Swap => "swap64",
        Reverse => "reverse64",
        Sbox => "sbox64",
        Not => "not",
        Add => $"add ror{k}",
        Sub => $"sub ror{k}",
        Xor => $"xor ror{k}",
        XorNot => $"xor ~ror{k}",
        RotR => $"rotr64 by (ror{k} % 63) + 1",
        RotL => $"rotl64 by (ror{k} % 63) + 1",
        _ => throw new ArgumentOutOfRangeException(nameof(kind)),
    };

    // Riot's 64-bit substitution table, a permutation of 0..255. Copied from
    // libraries/vrfnet/payload_transform.py, which asserts that property --
    // a truncated table is still valid hex and would fail silently.
    private const string SubstituteTableHex =
        "77B9042FEB7D27C944739A3F36F565DDF7E0302DA9985DDE69A394A05E170678" +
        "A4F6AB0343C828E56A8E1CF270CF5305D30DFFA7A23A32255A1F48C1B7E16E85" +
        "996047BBE48ACBC01BEA6164F0C2D88BCDFDADB819B5BF0E9181839D45D249E9" +
        "C731BD20BEC66680D179D7E6FCA15B5FDFF1D0506752FE7B3513F846B3758DE3" +
        "3E2EF4DC342A0823E20C094BEEC30F248F544C5539CC1D1E3B2272DA296B41AA" +
        "A6122C93CA9C970A56A87A9EB462923D9F38F3408437B2D4AF7633FA21EFFB71" +
        "6F9082511AC574F95907BA11B1ACD6EDE702AE9610167C4F881426BC1501684A" +
        "2B0B7FA54EE86DEC4DB05CC4009558B6D57E42DB5718866CCED99B89873C8C63";

    /// <summary>
    /// The substitution folded into eight shifted lookup tables, so applying it
    /// to a u64 is eight indexed reads and seven ORs rather than a round trip
    /// through a byte buffer. This is the hottest op in the search.
    /// </summary>
    public static readonly ulong[] SboxShifted = BuildSboxShifted();

    private static ulong[] BuildSboxShifted()
    {
        var table = Convert.FromHexString(SubstituteTableHex);
        if (table.Length != 256)
        {
            throw new InvalidOperationException($"substitution table holds {table.Length} bytes, need 256");
        }

        var seen = new bool[256];
        foreach (var b in table)
        {
            seen[b] = true;
        }

        if (Array.IndexOf(seen, false) >= 0)
        {
            throw new InvalidOperationException("substitution table is not a permutation of 0..255");
        }

        var shifted = new ulong[8 * 256];
        for (var lane = 0; lane < 8; lane++)
        {
            for (var value = 0; value < 256; value++)
            {
                shifted[(lane << 8) | value] = (ulong)table[value] << (8 * lane);
            }
        }

        return shifted;
    }

    public static ulong Sbox64(ulong v)
    {
        var t = SboxShifted;
        return t[(int)(v & 0xFF)]
             | t[0x100 | (int)((v >> 8) & 0xFF)]
             | t[0x200 | (int)((v >> 16) & 0xFF)]
             | t[0x300 | (int)((v >> 24) & 0xFF)]
             | t[0x400 | (int)((v >> 32) & 0xFF)]
             | t[0x500 | (int)((v >> 40) & 0xFF)]
             | t[0x600 | (int)((v >> 48) & 0xFF)]
             | t[0x700 | (int)((v >> 56) & 0xFF)];
    }

    /// <summary>Adjacent-bit swap: bit index XOR 1.</summary>
    public static ulong Swap64(ulong v) =>
        ((v & 0x5555555555555555UL) << 1) | ((v >> 1) & 0x5555555555555555UL);

    /// <summary>
    /// UE-style reversal that deliberately omits the final 16-bit swap, so it
    /// is bit index XOR 47 rather than a true reversal. Ported exactly from
    /// the Python, which ported it exactly from the parser: "close enough to a
    /// reversal" would decode nothing.
    /// </summary>
    public static ulong Reverse64(ulong v)
    {
        v = ((v & 0x5555555555555555UL) << 1) | ((v >> 1) & 0x5555555555555555UL);
        v = ((v & 0x3333333333333333UL) << 2) | ((v >> 2) & 0x3333333333333333UL);
        v = ((v & 0x0F0F0F0F0F0F0F0FUL) << 4) | ((v >> 4) & 0x0F0F0F0F0F0F0F0FUL);
        v = ((v & 0x00FF00FF00FF00FFUL) << 8) | ((v >> 8) & 0x00FF00FF00FF00FFUL);
        return (v << 32) | (v >> 32);
    }

    public static uint RotR32(uint v, int count) => (v >> count) | (v << (32 - count));
}
