using Replay.Encoding.Archives;
using Replay.Models.Descriptors;
using Replay.Models.Events;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Movement;

internal sealed class RemoteCharacterUpdatesRpcDecoder : IRpcDecoder
{
    private const int RemoteCharacterUpdatesHandle = 1;
    private const int ShooterCharacterNetGuidValueHandle = 2;
    private const int ComponentDataStreamHandle = 3;
    private const int MaxRemoteCharacterUpdates = 256;

    public static RemoteCharacterUpdatesRpcDecoder Instance { get; } = new();

    private RemoteCharacterUpdatesRpcDecoder()
    {
    }

    public DecodedPayloadResult Decode(ref FieldDecodeContext context, FBitArchive archive)
    {
        var endBit = archive.BitLength;
        if (!TryReadBit(archive, endBit))
        {
            return DecodedPayloadResult.Empty;
        }

        DecodedPayloadResult? result = null;
        while (archive.BitPosition < endBit)
        {
            var encodedHandle = ReadIntPacked(archive, endBit, nameof(RemoteCharacterUpdatesRpcDecoder));
            if (encodedHandle == 0)
            {
                break;
            }

            var handle = checked((int)encodedHandle - 1);
            var payloadBits = ReadIntPacked(archive, endBit, nameof(RemoteCharacterUpdatesRpcDecoder));
            var payloadEndBit = CheckedPayloadEnd(archive, endBit, payloadBits, nameof(RemoteCharacterUpdatesRpcDecoder));

            if (handle != RemoteCharacterUpdatesHandle)
            {
                archive.SeekBits(payloadEndBit);
                continue;
            }

            var batch = ReadRemoteCharacterUpdates(archive, payloadEndBit);
            archive.SeekBits(payloadEndBit);
            EmitMovementEvents(ref context, batch);

            var diagnostics = context.CaptureDiagnosticFields
                ? new[]
                {
                    new DecodedReplayField(
                        handle,
                        "RemoteCharacterUpdates",
                        "RemoteCharacterUpdates",
                        ExportCategory.Movement,
                        DecodedFieldValue.FromObject(batch)),
                }
                : [];

            result = new DecodedPayloadResult(batch, DecodedFieldCount: 1, diagnostics);
        }

        return result ?? DecodedPayloadResult.Empty;
    }

    private static RemoteCharacterUpdateBatch ReadRemoteCharacterUpdates(FBitArchive archive, long endBit)
    {
        var updateCount = ReadIntPacked(archive, endBit, nameof(ReadRemoteCharacterUpdates));
        if (updateCount > MaxRemoteCharacterUpdates)
        {
            throw new ArchiveReadException(
                ArchiveErrorCode.InvalidCount,
                nameof(ReadRemoteCharacterUpdates),
                archive.Position,
                archive.Length,
                updateCount);
        }

        var updates = new RemoteCharacterUpdate?[updateCount];
        while (archive.BitPosition < endBit)
        {
            var encodedIndex = ReadIntPacked(archive, endBit, nameof(ReadRemoteCharacterUpdates));
            if (encodedIndex == 0)
            {
                if (endBit - archive.BitPosition == 8)
                {
                    _ = ReadIntPacked(archive, endBit, nameof(ReadRemoteCharacterUpdates));
                }

                break;
            }

            var index = checked((int)encodedIndex - 1);
            if ((uint)index >= updateCount)
            {
                archive.SeekBits(endBit);
                break;
            }

            updates[index] = ReadRemoteCharacterUpdate(archive, endBit, index);
        }

        var batch = new RemoteCharacterUpdateBatch(checked((int)updateCount));
        foreach (var update in updates)
        {
            if (update is not null)
            {
                batch.AddUpdate(update);
            }
        }

        return batch;
    }

    private static RemoteCharacterUpdate ReadRemoteCharacterUpdate(FBitArchive archive, long endBit, int index)
    {
        var update = new RemoteCharacterUpdate { Index = index };
        while (archive.BitPosition < endBit)
        {
            var encodedHandle = ReadIntPacked(archive, endBit, nameof(ReadRemoteCharacterUpdate));
            if (encodedHandle == 0)
            {
                break;
            }

            var handle = checked((int)encodedHandle - 1);
            var payloadBits = ReadIntPacked(archive, endBit, nameof(ReadRemoteCharacterUpdate));
            var payloadEndBit = CheckedPayloadEnd(archive, endBit, payloadBits, nameof(ReadRemoteCharacterUpdate));

            switch (handle)
            {
                case ShooterCharacterNetGuidValueHandle:
                    if (!TryReadUInt32(archive, payloadEndBit, out var shooterGuid))
                    {
                        throw new ArchiveReadException(
                            ArchiveErrorCode.InvalidBitCount,
                            nameof(ReadRemoteCharacterUpdate),
                            archive.Position,
                            archive.Length,
                            payloadBits);
                    }

                    update.ShooterCharacterNetGuidValue = shooterGuid;
                    break;

                case ComponentDataStreamHandle:
                    update.ComponentDataStream = ComponentDataStream.Decode(archive, payloadEndBit);
                    break;
            }

            archive.SeekBits(payloadEndBit);
        }

        return update;
    }

    private static void EmitMovementEvents(ref FieldDecodeContext context, RemoteCharacterUpdateBatch batch)
    {
        if (context.EventSink is null or NullReplayEventSink)
        {
            return;
        }

        foreach (var update in batch.Updates)
        {
            if (update is not { ShooterCharacterNetGuidValue: { } shooterGuid, ComponentDataStream: { HasLatestMove: true } componentDataStream })
            {
                continue;
            }

            var moveIndex = componentDataStream.MoveCount - 1;
            var move = componentDataStream.LatestMove;

            context.EventSink.Emit(new RemoteCharacterMovementReceived(
                context.CurrentTimeSeconds,
                context.CurrentPacketId,
                context.ActorNetGuid.Value,
                context.ObjectNetGuid.Value,
                context.ChannelIndex,
                update.Index,
                shooterGuid,
                moveIndex,
                move));
        }
    }

    private static bool TryReadBit(FBitArchive archive, long endBit)
    {
        return archive.BitPosition < endBit && archive.TryReadBit(out _);
    }

    private static bool TryReadUInt32(FBitArchive archive, long endBit, out uint value)
    {
        if (endBit - archive.BitPosition >= 32)
        {
            value = (uint)archive.ReadBitsToUInt64(32);
            return true;
        }

        value = 0;
        return false;
    }

    private static uint ReadIntPacked(FBitArchive archive, long endBit, string operation) =>
        ComponentDataStream.ReadIntPackedForRpc(archive, endBit, operation);

    private static long CheckedPayloadEnd(FBitArchive archive, long endBit, uint payloadBits, string operation) =>
        ComponentDataStream.CheckedPayloadEndForRpc(archive, endBit, payloadBits, operation);
}