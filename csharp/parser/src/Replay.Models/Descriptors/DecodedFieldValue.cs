using Replay.Models.Unreal;

namespace Replay.Models.Descriptors;

public readonly record struct DecodedFieldValue
{
    private DecodedFieldValue(
        DecodedFieldValueKind kind,
        bool boolValue = false,
        byte byteValue = 0,
        int int32Value = 0,
        uint uint32Value = 0,
        ulong uint64Value = 0,
        float floatValue = 0,
        double doubleValue = 0,
        uint netGuidValue = 0,
        Guid guidValue = default,
        string? stringValue = null,
        FVector vectorValue = default,
        FRotator rotatorValue = default,
        FGameplayTag gameplayTagValue = default,
        FTransform transformValue = default,
        FRepMovement repMovement = default,
        object? objectValue = null)
    {
        Kind = kind;
        BoolValue = boolValue;
        ByteValue = byteValue;
        Int32Value = int32Value;
        UInt32Value = uint32Value;
        UInt64Value = uint64Value;
        FloatValue = floatValue;
        DoubleValue = doubleValue;
        NetGuidValue = netGuidValue;
        GuidValue = guidValue;
        StringValue = stringValue;
        VectorValue = vectorValue;
        RotatorValue = rotatorValue;
        RepMovementValue = repMovement;
        ObjectValue = objectValue;
        GameplayTagValue = gameplayTagValue;
        TransformValue = transformValue;
    }

    public static DecodedFieldValue None { get; } = new(DecodedFieldValueKind.None);

    public DecodedFieldValueKind Kind { get; }

    public bool BoolValue { get; }

    public byte ByteValue { get; }

    public int Int32Value { get; }

    public uint UInt32Value { get; }

    public ulong UInt64Value { get; }

    public float FloatValue { get; }

    public double DoubleValue { get; }

    public uint NetGuidValue { get; }
    public Guid GuidValue { get; }

    public string? StringValue { get; }

    public FVector VectorValue { get; }

    public FRotator RotatorValue { get; }

    public FRepMovement RepMovementValue { get; }
    public FGameplayTag GameplayTagValue { get; }
    public FTransform TransformValue { get; }

    public object? ObjectValue { get; }

    public bool HasValue => Kind != DecodedFieldValueKind.None;

    public static DecodedFieldValue FromBool(bool value) => new(DecodedFieldValueKind.Bool, boolValue: value);

    public static DecodedFieldValue FromByte(byte value) => new(DecodedFieldValueKind.Byte, byteValue: value);

    public static DecodedFieldValue FromInt32(int value) => new(DecodedFieldValueKind.Int32, int32Value: value);

    public static DecodedFieldValue FromUInt32(uint value) => new(DecodedFieldValueKind.UInt32, uint32Value: value);

    public static DecodedFieldValue FromUInt64(ulong value) => new(DecodedFieldValueKind.UInt64, uint64Value: value);

    public static DecodedFieldValue FromFloat(float value) => new(DecodedFieldValueKind.Float, floatValue: value);

    public static DecodedFieldValue FromDouble(double value) => new(DecodedFieldValueKind.Double, doubleValue: value);

    public static DecodedFieldValue FromNetGuid(uint value) => new(DecodedFieldValueKind.NetGuid, netGuidValue: value);

    public static DecodedFieldValue FromGuid(Guid value) => new(DecodedFieldValueKind.Guid, guidValue: value);

    public static DecodedFieldValue FromString(string value) => new(DecodedFieldValueKind.String, stringValue: value);

    public static DecodedFieldValue FromVector(FVector value) => new(DecodedFieldValueKind.Vector, vectorValue: value);

    public static DecodedFieldValue FromRotator(FRotator value) => new(DecodedFieldValueKind.Rotator, rotatorValue: value);

    public static DecodedFieldValue FromGameplayTag(FGameplayTag value) =>
        new(DecodedFieldValueKind.GameplayTag, gameplayTagValue: value);

    public static DecodedFieldValue FromTransform(FTransform value) =>
        new(DecodedFieldValueKind.Transform, transformValue: value);

    public static DecodedFieldValue FromRepMovement(FRepMovement value) =>
        new(DecodedFieldValueKind.RepMovement, repMovement: value);

    public static DecodedFieldValue FromObject(object value) => new(DecodedFieldValueKind.Object, objectValue: value);
}