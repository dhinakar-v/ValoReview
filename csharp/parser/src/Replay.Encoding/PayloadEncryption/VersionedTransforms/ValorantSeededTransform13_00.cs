using Replay.Encoding.Archives;
using static Replay.Encoding.PayloadEncryption.ValorantSeededTransformHelpers;

namespace Replay.Encoding.PayloadEncryption.VersionedTransforms;

public sealed class ValorantSeededTransform13_00 : IPayloadTransform
{
    private const uint SeedAddend = 0x2949b6efu;
    private const uint InitAOffset = 0x11u;
    private const byte TailXor = 0xef;

    public IReadOnlyCollection<string> SupportedReplayVersions { get; } = ["++Ares-Core+release-13.00"];

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
                var value = ReadUInt64(output, byteOffset);
                var ror1 = RotateRight(state, 1);
                var ror3 = RotateRight(state, 3);
                var ror6 = RotateRight(state, 6);
                var ror8 = RotateRight(state, 8);

                value += ror8;
                value = ReverseBits64WithoutFinal16BitSwap(value);
                value = (value + ror6) ^ ror3;
                value = SubstituteBytes(value, SubstituteTable64);
                value = RotateRight(value, (int)(ror1 % 63) + 1);

                WriteUInt64(output, byteOffset, value);
                AdvanceTransformState(ref state, ref prngA, ref prngB, out streamByte);
                byteOffset += 8;
                bitsRemaining -= 64;
            }

            while (bitsRemaining > 31)
            {
                var value = ReadUInt32(output, byteOffset);
                var rol1 = RotateLeft(state, 1);
                var rol3 = RotateLeft(state, 3);
                var rol6 = RotateLeft(state, 6);
                var rol8 = RotateLeft(state, 8);

                value += rol8;
                value = ReverseBits32(value);
                value = ~(value + rol6) ^ rol3;
                value = SubstituteBytes(value, SubstituteTable32);
                value = RotateRight(value, (int)(rol1 % 31) + 1);

                WriteUInt32(output, byteOffset, value);
                AdvanceTransformState(ref state, ref prngA, ref prngB, out streamByte);
                byteOffset += 4;
                bitsRemaining -= 32;
            }

            while (bitsRemaining > 7)
            {
                var value = output[byteOffset];
                var mix = state * 0x533u;

                value = (byte)(value + (byte)mix * 0x1b);
                value = ReverseBits8(value);
                value = (byte)(~(value + (byte)mix * 0x33) ^ (byte)mix);
                value = SubstituteTable8[value];
                value = RotateRight(value, (int)(state * 0x0bu % 7) + 1);

                output[byteOffset] = value;
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

    private static ulong InitialPrngA(uint seed)
    {
        unchecked
        {
            var seedPlus = seed + SeedAddend;
            var mixed = ((seedPlus >> 15) ^ seedPlus) >> 12 ^ ((seed - InitAOffset) * 0x02000000u) ^ seedPlus;
            return mixed * Multiplier;
        }
    }
}
