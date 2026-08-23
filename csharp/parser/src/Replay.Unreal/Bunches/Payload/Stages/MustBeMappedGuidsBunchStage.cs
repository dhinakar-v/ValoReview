using Microsoft.Extensions.Logging;
using Replay.Encoding.Archives;

namespace Replay.Unreal.Bunches.Payload.Stages;

internal sealed class MustBeMappedGuidsBunchStage : IBunchPayloadStage
{
    public BunchStageResult Process(ref BunchPayloadContext context)
    {
        if (!context.Header.bHasMustBeMappedGUIDs)
        {
            return BunchStageResult.Continue;
        }

        try
        {
            ReadMustBeMappedGuids(context.Payload, context.Stats);
            return BunchStageResult.Continue;
        }
        catch (ArchiveReadException exception)
        {
            context.ReaderContext.LoggerFactory?
                .CreateLogger<MustBeMappedGuidsBunchStage>()
                .LogError(
                    exception,
                    "Failed to parse must-be-mapped GUIDs in packet {PacketId} on channel {ChannelIndex} at payload position {PayloadPosition} of {PayloadLength} bits.",
                    context.Header.PacketId,
                    context.Header.ChIndex,
                    context.Payload.Position,
                    context.Payload.Length);
            context.Stats.MalformedPayloadCount++;
            context.Stats.MalformedMustBeMappedGuidCount++;
            context.Payload.SkipRemaining();
            return BunchStageResult.Stop;
        }
    }

    private static void ReadMustBeMappedGuids(FBitArchive payload, BunchPayloadStats stats)
    {
        var count = payload.ReadUInt16();
        for (var i = 0; i < count; i++)
        {
            _ = payload.ReadIntPacked();
            stats.MustBeMappedGuidCount++;
        }
    }
}
