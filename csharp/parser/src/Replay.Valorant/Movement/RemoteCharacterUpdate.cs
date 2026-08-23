namespace Replay.Valorant.Movement;

public sealed class RemoteCharacterUpdate
{
    public int Index { get; init; }
    public uint? ShooterCharacterNetGuidValue { get; set; }
    public ComponentDataStream? ComponentDataStream { get; set; }

    public override string ToString() =>
        $"Guid={ShooterCharacterNetGuidValue}|ComponentDataStream={ComponentDataStream}";
}