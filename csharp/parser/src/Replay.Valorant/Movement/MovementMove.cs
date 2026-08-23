using Replay.Models.Unreal;

namespace Replay.Valorant.Movement;

public readonly record struct MovementMove(
    int Marker,
    byte MoveType,
    FVector Position,
    FVector? Velocity,
    FVector RotationInput,
    FVector? Variant1Vector,
    uint Timestamp,
    byte ModeFlags,
    byte MovementState,
    sbyte RotationYawMultiplier,
    byte UnusedByte,
    bool HasOptionalMovementValue,
    byte? OptionalMovementRawByte,
    double? OptionalMovementValue,
    bool Flag48,
    uint PackedAngles,
    ushort RawYaw,
    ushort RawPitch,
    double Yaw,
    double Pitch,
    bool? Variant0HasExternalCharacterRef,
    uint? Variant0PackedAngles,
    bool? Variant1Flag,
    bool ErrorSentinel);