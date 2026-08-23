namespace Replay.Valorant.Combat;

public sealed record ValorantEquippable(
    uint NetGuid,
    string? Name,
    ValorantEquippableCategory Category,
    string? ClassPath);