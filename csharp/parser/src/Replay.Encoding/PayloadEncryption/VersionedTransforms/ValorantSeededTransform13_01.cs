using Replay.Encoding.Archives;
using static Replay.Encoding.PayloadEncryption.ValorantSeededTransformHelpers;

namespace Replay.Encoding.PayloadEncryption.VersionedTransforms;

public sealed class ValorantSeededTransform13_01 : IPayloadTransform
{
    private const uint SeedAddend = 0xe62fcd5cu;
    private const uint InitAOffset = 0x24u;
    private const byte TailXor = 0x5c;

    public IReadOnlyCollection<string> SupportedReplayVersions { get; } = ["++Ares-Core+release-13.01"];

    public int GetOutputByteCount(int bitCount) => ValorantSeededTransformHelpers.GetOutputByteCount(bitCount);

    public void Apply(FBitArchive input, uint seed, Span<byte> output)
    {
        var bitCount = CopyInputToOutput(input, output);
        Transform(output[..GetOutputByteCount(bitCount)], bitCount, seed);
    }

    public void Apply(FBitArchive input, int bitCount, uint seed, Span<byte> output)
    {
        CopyInputToOutput(input, bitCount, output);
        Transform(output[..GetOutputByteCount(bitCount)], bitCount, seed);
    }

    private static void Transform(Span<byte> output, int bitCount, uint seed)
    {
        if (bitCount == 0)
        {
            return;
        }

        var state = seed;
        var streamByte = (byte)seed;
        var prngA = InitialPrngA(seed);
        var prngB = InitialPrngB(seed);
        var byteOffset = 0;
        var bitsRemaining = bitCount;

        unchecked
        {
            while (bitsRemaining > 63)
            {
                var value = TransformUInt64(ReadUInt64(output, byteOffset), state);
                WriteUInt64(output, byteOffset, value);
                AdvanceTransformState(ref state, ref prngA, ref prngB, out streamByte);
                byteOffset += 8;
                bitsRemaining -= 64;
            }

            while (bitsRemaining > 31)
            {
                var value = TransformUInt32(ReadUInt32(output, byteOffset), state);
                WriteUInt32(output, byteOffset, value);
                AdvanceTransformState(ref state, ref prngA, ref prngB, out streamByte);
                byteOffset += 4;
                bitsRemaining -= 32;
            }

            while (bitsRemaining > 7)
            {
                output[byteOffset] = TransformByte(output[byteOffset], state);
                AdvanceTransformState(ref state, ref prngA, ref prngB, out streamByte);
                byteOffset++;
                bitsRemaining -= 8;
            }

            if (bitsRemaining != 0)
            {
                var mask = (byte)(0xff >> (7 - ((bitCount - 1) & 7)));
                output[byteOffset] ^= (byte)(mask & (streamByte ^ TailXor));
            }
        }
    }

    private static ulong TransformUInt64(ulong value, uint state)
    {
        unchecked
        {
            value = SwapAdjacentBits(~value) ^ ~(ulong)RotateRight(state, 5);
            value = ~RotateRight(value, (int)(RotateRight(state, 4) % 63) + 1);
            return value + RotateRight(state, 1);
        }
    }

    private static uint TransformUInt32(uint value, uint state)
    {
        unchecked
        {
            value = SwapAdjacentBits(~value) ^ RotateLeft(state, 5);
            value = ~RotateRight(value, (int)(RotateLeft(state, 4) % 31) + 1);
            return value + RotateLeft(state, 1);
        }
    }

    private static byte TransformByte(byte value, uint state)
    {
        unchecked
        {
            var state11 = state * 0x0bu;
            var mix = state11 * 0x533u;
            value = (byte)(SwapAdjacentBits((byte)~value) ^ (byte)(mix * 0x0bu));
            value = (byte)~RotateRight(value, (int)(mix % 7) + 1);
            return (byte)(value + (byte)state11);
        }
    }

    private static ulong InitialPrngA(uint seed)
    {
        unchecked
        {
            var seedPlus = seed + SeedAddend;
            var mixed = ((seedPlus >> 15) ^ seedPlus) >> 12 ^
                        ((seed - InitAOffset) * 0x02000000u) ^
                        seedPlus;
            return mixed * Multiplier;
        }
    }

}
