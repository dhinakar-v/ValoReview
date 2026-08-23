namespace Replay.Unreal.Bunches.Payload.Stages;

internal sealed class ActorChannelLookupBunchStage : IBunchPayloadStage
{
    public BunchStageResult Process(ref BunchPayloadContext context)
    {
        context.ReaderContext.ChannelStates.TryGetValue(context.Header.ChIndex, out var channel);
        context.Channel = channel is { IsOpen: true } ? channel : null;
        return BunchStageResult.Continue;
    }
}
