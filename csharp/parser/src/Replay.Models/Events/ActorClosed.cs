using Replay.Models.Net;

namespace Replay.Models.Events;

public sealed record ActorClosed(
    float TimeSeconds,
    int PacketId,
    uint ActorNetGuid,
    uint ChannelIndex,
    ChannelCloseReason Reason)
    : ReplayEvent(TimeSeconds, PacketId);