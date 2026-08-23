using Microsoft.Extensions.Logging;
using Replay.Encoding.Archives;

namespace Replay.Unreal.Bunches.Payload.Stages;

internal sealed class ContentBlocksBunchStage : IBunchPayloadStage
{
    private readonly ContentBlockFramer _contentBlockFramer;

    public ContentBlocksBunchStage(ContentBlockFramer contentBlockFramer)
    {
        _contentBlockFramer = contentBlockFramer;
    }

    public BunchStageResult Process(ref BunchPayloadContext context)
    {
        if (context.Payload.AtEnd)
        {
            return BunchStageResult.Continue;
        }

        if (context.Channel is null)
        {
            context.Payload.SkipRemaining();
            return BunchStageResult.Continue;
        }

        try
        {
            _contentBlockFramer.FrameContentBlocks(
                context.Payload,
                context.Channel,
                context.Stats,
                context.ReaderContext.CurrentTimeSeconds,
                context.Header.PacketId,
                context.ReaderContext.ReplayVersion.Branch);
            return BunchStageResult.Continue;
        }
        catch (ArchiveReadException exception)
        {
            context.ReaderContext.LoggerFactory?
                .CreateLogger<ContentBlocksBunchStage>()
                .LogError(
                    exception,
                    "Failed to parse content blocks in packet {PacketId} on channel {ChannelIndex} at payload position {PayloadPosition} of {PayloadLength} bits.",
                    context.Header.PacketId,
                    context.Header.ChIndex,
                    context.Payload.Position,
                    context.Payload.Length);
            context.Stats.MalformedPayloadCount++;
            context.Stats.MalformedPayloadExceptionCount++;
            return BunchStageResult.Stop;
        }
    }
}
