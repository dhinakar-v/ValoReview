using Replay.Models.Events;

namespace Replay.Valorant.Combat;

public sealed record ValorantShotReceived(
    float TimeSeconds,
    int PacketId,
    uint ActorNetGuid,
    uint ObjectNetGuid,
    uint ChannelIndex,
    ValorantShot Shot)
    : ReplayEvent(TimeSeconds, PacketId);