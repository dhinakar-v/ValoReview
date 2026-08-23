using Replay.Encoding.Archives;
using Replay.Models.Unreal;

namespace Replay.Valorant.Movement;

public sealed class ComponentDataStream
{
    private const byte MovementMagic = 0x52;
    private const double FixedVectorScale = 1.0 / 65536.0;
    private const double OptionalByteScale = 1.0;
    private const double AngleScale = 360.0 / 65536.0;
    private const int MaxMovementPaddingBits = 31;

    public bool HasMovementSection { get; private set; }
    public bool HasValidMovementMagic { get; private set; }
    public string? MovementParseError { get; private set; }
    public int MoveCount { get; private set; }
    public bool HasLatestMove { get; private set; }
    public MovementMove LatestMove { get; private set; }

    public static ComponentDataStream Decode(FBitArchive archive)
    {
        var stream = new ComponentDataStream();
        stream.Parse(archive, archive.BitLength);
        return stream;
    }

    internal static ComponentDataStream Decode(FBitArchive archive, long endBit)
    {
        var stream = new ComponentDataStream();
        stream.Parse(archive, endBit);
        return stream;
    }

    public override string ToString() =>
        $"moves={MoveCount}, error={MovementParseError ?? "<none>"}";

    private void Parse(FBitArchive archive, long endBit)
    {
        if (TryParseByteWrappedPayload(archive, endBit))
        {
            return;
        }

        ParseComponentPayload(archive, endBit);
    }

    private bool TryParseByteWrappedPayload(FBitArchive archive, long endBit)
    {
        using var checkpoint = archive.CreateCheckpoint();

        if (!TryReadUInt16(archive, endBit, out var byteCount) ||
            byteCount == 0 ||
            BitsRemaining(archive, endBit) < byteCount * 8L)
        {
            return false;
        }

        var payloadEndBit = archive.BitPosition + byteCount * 8L;
        ParseComponentPayload(archive, payloadEndBit);
        archive.SeekBits(payloadEndBit);
        checkpoint.Commit();
        return true;
    }

    private void ParseComponentPayload(FBitArchive archive, long componentEndBit)
    {
        if (!TryReadUInt16(archive, componentEndBit, out var movementBitCount))
        {
            return;
        }

        var remainingBits = BitsRemaining(archive, componentEndBit);
        if (movementBitCount == 0 || movementBitCount > remainingBits)
        {
            HasMovementSection = true;
            ParseMovementSection(archive, componentEndBit);
            archive.SeekBits(componentEndBit);
            return;
        }

        HasMovementSection = true;

        var movementEndBit = archive.BitPosition + movementBitCount;
        ParseMovementSection(archive, movementEndBit);
        archive.SeekBits(movementEndBit);

        if (archive.BitPosition >= componentEndBit) return;
        archive.SeekBits(componentEndBit);
    }

    private void ParseMovementSection(FBitArchive archive, long endBit)
    {
        if (!TryReadByte(archive, endBit, out var magic))
        {
            MovementParseError = "Missing movement magic";
            return;
        }

        HasValidMovementMagic = magic == MovementMagic;
        if (!HasValidMovementMagic)
        {
            MovementParseError = $"Invalid movement magic 0x{magic:X2}";
            archive.SeekBits(endBit);
            return;
        }

        var expectedMarker = 1;
        if (!TryReadBits(archive, endBit, 3, out var marker))
        {
            MovementParseError = "Missing first movement marker";
            return;
        }

        while (marker != 0)
        {
            if (marker != expectedMarker)
            {
                MovementParseError = $"Movement marker mismatch: expected {expectedMarker}, got {marker}";
                archive.SeekBits(endBit);
                return;
            }

            if (!TryReadMove(archive, endBit, marker, out var move, out var error))
            {
                MovementParseError = error ?? "Invalid movement record";
                archive.SeekBits(endBit);
                return;
            }

            MoveCount++;
            LatestMove = move;
            HasLatestMove = true;

            if (BitsRemaining(archive, endBit) <= MaxMovementPaddingBits)
            {
                return;
            }

            expectedMarker = NextMarker(expectedMarker);
            if (!TryReadBits(archive, endBit, 3, out marker))
            {
                MovementParseError = "Missing next movement marker";
                return;
            }
        }
    }

    private static bool TryReadMove(
        FBitArchive archive,
        long endBit,
        int marker,
        out MovementMove move,
        out string? error)
    {
        move = default;
        error = null;

        if (!TryReadBitsToUInt64(archive, endBit, 25, out var header))
        {
            error = "Missing movement record header";
            return false;
        }

        var moveType = (header & 1UL) != 0;
        var rotationYawMultiplier = (byte)(header >> 1);
        var movementState = (byte)(header >> 9);
        var unusedByte = (byte)(header >> 17);

        if (!TryReadFixedVector(archive, endBit, out var rotationInput) ||
            !TryReadVLQ(archive, endBit, out var timestamp) ||
            !TryReadQuantizedVector(archive, endBit, 100, out var position))
        {
            error = "Missing movement common vector/timestamp fields";
            return false;
        }

        if (!TryReadBit(archive, endBit, out var hasOptionalByte))
        {
            error = "Missing optional movement value flag";
            return false;
        }

        byte? optionalRawByte = null;
        double? optionalValue = null;
        if (hasOptionalByte)
        {
            if (!TryReadByte(archive, endBit, out var optionalByte))
            {
                error = "Missing optional movement value";
                return false;
            }

            optionalRawByte = optionalByte;
            optionalValue = optionalByte * OptionalByteScale;
        }

        if (!TryReadBitsToUInt64(archive, endBit, 33, out var flagAndPackedAngles))
        {
            error = "Missing movement flag/angle fields";
            return false;
        }

        var flag48 = (flagAndPackedAngles & 1UL) != 0;
        var packedAngles = (uint)(flagAndPackedAngles >> 1);
        var pitch = (ushort)(packedAngles & 0xFFFF);
        var yaw = (ushort)(packedAngles >> 16);

        FVector? velocity = null;
        FVector? variant1Vector = null;
        bool? variant1Flag = null;
        bool? variant0HasExternalCharacterRef = null;
        uint? variant0PackedAngles = null;

        if (moveType)
        {
            if (!TryReadBit(archive, endBit, out var readVariant1Flag) ||
                !TryReadQuantizedVector(archive, endBit, 10, out var readVariant1Vector))
            {
                error = "Missing variant-1 movement fields";
                return false;
            }

            variant1Flag = readVariant1Flag;
            variant1Vector = readVariant1Vector;
            velocity = readVariant1Vector;
        }
        else if (!TryReadVariant0Extra(
                     archive,
                     endBit,
                     out variant0HasExternalCharacterRef,
                     out variant0PackedAngles,
                     out error))
        {
            return false;
        }

        if (!TryReadBit(archive, endBit, out var errorSentinel))
        {
            error = "Missing movement error sentinel";
            return false;
        }

        move = new MovementMove(
            marker,
            moveType ? (byte)1 : (byte)0,
            position,
            velocity,
            rotationInput,
            variant1Vector,
            timestamp,
            movementState,
            movementState,
            unchecked((sbyte)rotationYawMultiplier),
            unusedByte,
            hasOptionalByte,
            optionalRawByte,
            optionalValue,
            flag48,
            packedAngles,
            yaw,
            pitch,
            yaw * AngleScale,
            pitch * AngleScale,
            variant0HasExternalCharacterRef,
            variant0PackedAngles,
            variant1Flag,
            errorSentinel);

        if (errorSentinel)
        {
            error = "Movement error sentinel was set";
        }

        return !errorSentinel;
    }

    private static bool TryReadVariant0Extra(
        FBitArchive archive,
        long endBit,
        out bool? hasExternalCharacterRef,
        out uint? packedAngles,
        out string? error)
    {
        hasExternalCharacterRef = null;
        packedAngles = null;
        error = null;

        if (!TryReadBitsToUInt64(archive, endBit, 33, out var flagAndAngles))
        {
            error = "Missing variant-0 packed angle dword";
            return false;
        }

        hasExternalCharacterRef = (flagAndAngles & 1UL) != 0;
        if (hasExternalCharacterRef.Value)
        {
            error = "Variant-0 external character reference is not decoded yet";
            return false;
        }

        packedAngles = (uint)(flagAndAngles >> 1);
        return true;
    }

    private static bool TryReadFixedVector(FBitArchive archive, long endBit, out FVector vector)
    {
        vector = default;
        if (!TryReadBitsToUInt64(archive, endBit, 48, out var bits))
        {
            return false;
        }

        var x = (uint)(bits & 0xFFFF);
        var y = (uint)((bits >> 16) & 0xFFFF);
        var z = (uint)((bits >> 32) & 0xFFFF);

        vector = new FVector(
            ((int)x - 0x8000) * FixedVectorScale,
            ((int)y - 0x8000) * FixedVectorScale,
            ((int)z - 0x8000) * FixedVectorScale)
        {
            ScaleFactor = 65536,
            Bits = 16,
        };
        return true;
    }

    private static bool TryReadQuantizedVector(FBitArchive archive, long endBit, int scaleFactor, out FVector vector)
    {
        vector = default;
        if (!TryReadBitsToUInt64(archive, endBit, 7, out var componentBitCountAndExtraInfo))
        {
            return false;
        }

        var componentBits = (int)(componentBitCountAndExtraInfo & 63U);
        var extraInfo = componentBitCountAndExtraInfo >> 6;

        if (componentBits > 0)
        {
            if (!TryReadSignedQuantizedComponents(archive, endBit, componentBits, out var x, out var y, out var z))
            {
                return false;
            }

            vector = new FVector(
                extraInfo > 0 ? x / (double)scaleFactor : x,
                extraInfo > 0 ? y / (double)scaleFactor : y,
                extraInfo > 0 ? z / (double)scaleFactor : z)
            {
                Bits = componentBits,
                ScaleFactor = scaleFactor,
            };
            return true;
        }

        if (extraInfo == 0)
        {
            if (!TryReadSingle(archive, endBit, out var x) ||
                !TryReadSingle(archive, endBit, out var y) ||
                !TryReadSingle(archive, endBit, out var z))
            {
                return false;
            }

            vector = new FVector(x, y, z)
            {
                Bits = 32,
                ScaleFactor = scaleFactor,
            };
            return true;
        }

        if (!TryReadDouble(archive, endBit, out var dx) ||
            !TryReadDouble(archive, endBit, out var dy) ||
            !TryReadDouble(archive, endBit, out var dz))
        {
            return false;
        }

        vector = new FVector(dx, dy, dz)
        {
            Bits = 64,
            ScaleFactor = scaleFactor,
        };
        return true;
    }

    private static bool TryReadSignedQuantizedComponents(
        FBitArchive archive,
        long endBit,
        int componentBits,
        out long x,
        out long y,
        out long z)
    {
        x = 0;
        y = 0;
        z = 0;
        if (componentBits <= 0 || componentBits > 62)
        {
            return false;
        }

        var totalBits = checked(componentBits * 3);
        if (totalBits <= 64)
        {
            if (!TryReadBitsToUInt64(archive, endBit, totalBits, out var raw))
            {
                return false;
            }

            var mask = (1UL << componentBits) - 1UL;
            x = SignExtend(raw & mask, componentBits);
            y = SignExtend((raw >> componentBits) & mask, componentBits);
            z = SignExtend((raw >> (componentBits * 2)) & mask, componentBits);
            return true;
        }

        return TryReadSignedQuantizedComponent(archive, endBit, componentBits, out x) &&
               TryReadSignedQuantizedComponent(archive, endBit, componentBits, out y) &&
               TryReadSignedQuantizedComponent(archive, endBit, componentBits, out z);
    }

    private static bool TryReadSignedQuantizedComponent(
        FBitArchive archive,
        long endBit,
        int componentBits,
        out long value)
    {
        value = 0;
        if (componentBits <= 0 || componentBits > 62)
        {
            return false;
        }

        if (!TryReadBitsToUInt64(archive, endBit, componentBits, out var raw))
        {
            return false;
        }

        value = SignExtend(raw, componentBits);
        return true;
    }

    private static bool TryReadVLQ(FBitArchive archive, long endBit, out uint value)
    {
        value = 0;
        var shift = 0;

        while (true)
        {
            if (!TryReadByte(archive, endBit, out var b))
            {
                return false;
            }

            value |= (uint)(((b >> 1) & 0x7F) << shift);
            if ((b & 1) == 0)
            {
                return true;
            }

            shift += 7;
            if (shift >= 32)
            {
                return false;
            }
        }
    }

    private static bool TryReadSingle(FBitArchive archive, long endBit, out float value)
    {
        value = 0;
        if (!TryReadUInt32(archive, endBit, out var bits))
        {
            return false;
        }

        value = BitConverter.UInt32BitsToSingle(bits);
        return true;
    }

    private static bool TryReadDouble(FBitArchive archive, long endBit, out double value)
    {
        value = 0;
        if (!TryReadBitsToUInt64(archive, endBit, 64, out var bits))
        {
            return false;
        }

        value = BitConverter.UInt64BitsToDouble(bits);
        return true;
    }

    private static bool TryReadBit(FBitArchive archive, long endBit, out bool value)
    {
        if (TryReadBitsToUInt64(archive, endBit, 1, out var bits))
        {
            value = bits != 0;
            return true;
        }

        value = false;
        return false;
    }

    private static bool TryReadBits(FBitArchive archive, long endBit, int bitCount, out int value)
    {
        value = 0;
        if (!TryReadBitsToUInt64(archive, endBit, bitCount, out var bits))
        {
            return false;
        }

        value = (int)bits;
        return true;
    }

    private static bool TryReadByte(FBitArchive archive, long endBit, out byte value)
    {
        if (TryReadBitsToUInt64(archive, endBit, 8, out var bits))
        {
            value = (byte)bits;
            return true;
        }

        value = 0;
        return false;
    }

    private static bool TryReadUInt16(FBitArchive archive, long endBit, out ushort value)
    {
        if (TryReadBitsToUInt64(archive, endBit, 16, out var bits))
        {
            value = (ushort)bits;
            return true;
        }

        value = 0;
        return false;
    }

    private static bool TryReadUInt32(FBitArchive archive, long endBit, out uint value)
    {
        if (TryReadBitsToUInt64(archive, endBit, 32, out var bits))
        {
            value = (uint)bits;
            return true;
        }

        value = 0;
        return false;
    }

    private static bool TryReadBitsToUInt64(FBitArchive archive, long endBit, int bitCount, out ulong value)
    {
        if ((uint)bitCount > 64 || BitsRemaining(archive, endBit) < bitCount)
        {
            value = 0;
            return false;
        }

        value = archive.ReadBitsToUInt64(bitCount);
        return true;
    }

    private static long BitsRemaining(FBitArchive archive, long endBit) => endBit - archive.BitPosition;

    private static long CheckedPayloadEnd(FBitArchive archive, long endBit, uint payloadBits, string operation)
    {
        if (payloadBits > int.MaxValue || BitsRemaining(archive, endBit) < payloadBits)
        {
            throw new ArchiveReadException(
                ArchiveErrorCode.InvalidBitCount,
                operation,
                archive.Position,
                archive.Length,
                payloadBits);
        }

        return archive.BitPosition + payloadBits;
    }

    private static uint ReadIntPacked(FBitArchive archive, long endBit, string operation)
    {
        if (!TryReadIntPacked(archive, endBit, out var value))
        {
            throw new ArchiveReadException(
                ArchiveErrorCode.MalformedPackedInteger,
                operation,
                archive.Position,
                archive.Length,
                0);
        }

        return value;
    }

    private static bool TryReadIntPacked(FBitArchive archive, long endBit, out uint value)
    {
        value = 0;
        var shift = 0;

        for (var i = 0; i < 5; i++)
        {
            if (!TryReadByte(archive, endBit, out var nextByte))
            {
                return false;
            }

            value |= (uint)(nextByte >> 1) << shift;
            if ((nextByte & 1) == 0)
            {
                return true;
            }

            shift += 7;
        }

        return false;
    }

    private static long SignExtend(ulong raw, int bitCount)
    {
        var signBit = 1UL << (bitCount - 1);
        return (long)(raw ^ signBit) - (long)signBit;
    }

    private static int NextMarker(int marker)
    {
        var next = (marker + 1) & 7;
        return next < 2 ? 1 : next;
    }

    internal static uint ReadIntPackedForRpc(FBitArchive archive, long endBit, string operation) =>
        ReadIntPacked(archive, endBit, operation);

    internal static long CheckedPayloadEndForRpc(FBitArchive archive, long endBit, uint payloadBits, string operation) =>
        CheckedPayloadEnd(archive, endBit, payloadBits, operation);
}