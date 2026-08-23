using Replay.Models.Unreal;

namespace Replay.Valorant.Combat;

public sealed record ValorantShot(
    ulong? EffectId,
    float? StartMovementTime,
    string? SourceId,
    bool? IsLocalEffect,
    bool? IsTransient,
    uint? WaitOnReplicationActor,
    EAresAlliance? AllianceFilter,
    FVector? Location,
    FRotator? Rotation,
    float? AmmoRemaining,
    float? NumProjectiles,
    float? RandomSeed,
    float? TracerOption,
    float? BurstShotNumber,
    float? YawSwitch,
    uint? FiringPlayerState,
    uint? FiringState,
    IReadOnlyList<FVector> AttackVectors,
    uint? EffectEquippable,
    ValorantEquippable? Equippable,
    ValorantShotFireMode FireMode = ValorantShotFireMode.Unknown,
    string? FireModeEvidence = null);

public enum ValorantShotFireMode
{
    Unknown,
    Primary,
    Alternate,
}
