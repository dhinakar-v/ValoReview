using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Replay.Encoding.Archives;
using Replay.Models.Descriptors;
using Replay.Models.Events;

namespace Replay.Unreal.Parsing;

public class FieldPayloadParser
{
    public DecodedPayloadResult ParseContentPayload(
        FBitArchive payload,
        BoundExportGroup boundGroup,
        ref FieldDecodeContext context) =>
        ParseRepLayoutProperties(payload, boundGroup, ref context);

    public DecodedPayloadResult ParseRepLayoutProperties(
        FBitArchive payload,
        BoundExportGroup boundGroup,
        ref FieldDecodeContext context,
        bool readPropertyChecksum = true)
    {
        if (boundGroup.Grammar is FieldStreamGrammar.ClassNetCache)
        {
            GetLogger(context).LogWarning(
                "Export group '{ExportGroupPath}' cannot be parsed with class-net-cache grammar as content payload.",
                context.ExportGroupPath ?? boundGroup.SourceDescriptor.Path);
            payload.SkipRemaining();
            return DecodedPayloadResult.Empty;
        }

        if (readPropertyChecksum)
        {
            _ = payload.ReadBit();
        }

        context.CaptureDiagnosticFields = boundGroup.CaptureDiagnosticFields;
        var payloadObject = boundGroup.CreatePayloadInstance();
        var decodedFieldCount = 0;
        List<DecodedReplayField>? diagnosticFields = context.CaptureDiagnosticFields ? [] : null;
        while (!payload.AtEnd)
        {
            if (boundGroup.Grammar is FieldStreamGrammar.FunctionParameters && payload.BitsRemaining == 1)
            {
                payload.SkipBits(1);
                break;
            }

            if (ParseProperty(payload, boundGroup, payloadObject, ref context, ref decodedFieldCount, diagnosticFields))
            {
                return CreateDecodedPayloadResult(payloadObject, decodedFieldCount, diagnosticFields ?? [],
                    ref context);
            }
        }

        return CreateDecodedPayloadResult(payloadObject, decodedFieldCount, diagnosticFields ?? [], ref context);
    }

    public IReadOnlyList<DecodedRpcInvocation> ParseClassNetCachePayload(
        FBitArchive payload,
        BoundClassNetCache boundCache,
        ref FieldDecodeContext context)
    {
        if (boundCache.Grammar is not FieldStreamGrammar.ClassNetCache)
        {
            GetLogger(context).LogWarning(
                "Class net cache '{BoundCachePath}' has unsupported grammar '{FieldStreamGrammar}'.",
                boundCache.Path,
                boundCache.Grammar);
            payload.SkipRemaining();
            return [];
        }

        if (boundCache.FunctionsByHandle.Length == 0)
        {
            payload.SkipRemaining();
            return [];
        }

        var invocations = new List<DecodedRpcInvocation>();
        while (!payload.AtEnd)
        {
            var handle = (int)payload.ReadSerializedInt(boundCache.FunctionsByHandle.Length);
            if (payload.BitsRemaining < 8)
            {
                payload.SkipRemaining();
                return invocations;
            }

            var payloadBits = payload.ReadIntPacked();
            if (payloadBits > int.MaxValue || payload.BitsRemaining < payloadBits)
            {
                GetLogger(context).LogWarning(
                    "Malformed class net cache payload: handle={Handle}, bits={PayloadBits}, remaining={PayloadBitsRemaining}",
                    handle,
                    payloadBits,
                    payload.BitsRemaining);
                payload.SkipRemaining();
                return invocations;
            }

            BoundRpcFunction? rpcFunction = null;
            if ((uint)handle < boundCache.FunctionsByHandle.Length)
            {
                rpcFunction = boundCache.FunctionsByHandle[handle];
            }

            var rpcPayload = payload.ReadSubArchive((int)payloadBits);
            if (rpcFunction is null || !rpcFunction.Enabled)
            {
                rpcPayload.SkipRemaining();
                continue;
            }

            context.FieldName = rpcFunction.Name;
            context.Categories = rpcFunction.Categories;
            context.CaptureDiagnosticFields = rpcFunction.CaptureDiagnosticFields;

            var beforeRpc = rpcPayload.BitsRemaining;
            DecodedPayloadResult result;
            var wasDecoded = true;

            if (rpcFunction.Decoder is not null)
            {
                result = rpcFunction.Decoder.Decode(ref context, rpcPayload);
                if (!rpcPayload.AtEnd)
                {
                    rpcPayload.EnsureFullyConsumed($"RPC '{rpcFunction.Name}' (handle {handle})");
                }
            }
            else if (rpcFunction.FunctionGroup is { Enabled: true })
            {
                result = ParseRepLayoutProperties(
                    rpcPayload,
                    rpcFunction.FunctionGroup,
                    ref context,
                    readPropertyChecksum: true);
            }
            else
            {
                rpcPayload.SkipRemaining();
                result = DecodedPayloadResult.Empty;
                wasDecoded = false;
            }

            invocations.Add(new DecodedRpcInvocation(
                handle,
                rpcFunction.Name,
                rpcFunction.FunctionExportPath,
                rpcFunction.Categories,
                (int)payloadBits,
                checked((int)(beforeRpc - rpcPayload.BitsRemaining)),
                wasDecoded,
                result.Payload,
                result.DecodedFieldCount,
                result.DiagnosticFields));
        }

        return invocations;
    }

    private bool ParseProperty(
        FBitArchive payload,
        BoundExportGroup boundGroup,
        object payloadObject,
        ref FieldDecodeContext context,
        ref int decodedFieldCount,
        List<DecodedReplayField>? diagnosticFields)
    {
        var encodedHandle = payload.ReadIntPacked();
        if (encodedHandle == 0)
        {
            return true;
        }

        var handle = checked((int)(encodedHandle - 1));
        var payloadBits = payload.ReadIntPacked();
        if (payloadBits == 0)
        {
            return false;
        }

        if (payloadBits > int.MaxValue || payload.BitsRemaining < payloadBits)
        {
            GetLogger(context).LogWarning(
                "Malformed field payload: handle={Handle}, bits={PayloadBits}, remaining={PayloadBitsRemaining}",
                handle,
                payloadBits,
                payload.BitsRemaining);
            payload.SkipRemaining();
            return true;
        }

        var fieldBinding = GetBinding(handle, boundGroup);
        if (!fieldBinding.Enabled || fieldBinding.Decoder is null)
        {
            payload.SkipBits(payloadBits);
            return false;
        }

        context.FieldName = fieldBinding.Name;
        context.Categories = fieldBinding.Categories;

        var fieldPayload = payload.ReadSubArchive((int)payloadBits);
        try
        {
            var decodedValue = fieldBinding.Decoder.Decode(ref context, fieldPayload);
            if (!fieldPayload.AtEnd)
            {
                fieldPayload.EnsureFullyConsumed($"field '{fieldBinding.Name}' (handle {handle})");
            }

            if (decodedValue.HasValue)
            {
                DecodedValueAssigner.Assign(payloadObject, fieldBinding, decodedValue);
                decodedFieldCount++;
                diagnosticFields?.Add(new DecodedReplayField(
                    handle,
                    fieldBinding.Name,
                    fieldBinding.ExportName,
                    fieldBinding.Categories,
                    decodedValue));
            }
        }
        catch (Exception exception)
        {
            GetLogger(context).LogError(
                exception,
                "Failed to decode field '{FieldName}' (export '{ExportName}', handle {Handle}) in export group " +
                "'{ExportGroupPath}' for packet {PacketId} on channel {ChannelIndex} at field payload position " +
                "{FieldPayloadPosition} of {FieldPayloadLength} bits.",
                fieldBinding.Name,
                fieldBinding.ExportName,
                handle,
                context.ExportGroupPath ?? boundGroup.SourceDescriptor.Path,
                context.CurrentPacketId,
                context.ChannelIndex,
                fieldPayload.Position,
                fieldPayload.Length);
            throw;
        }

        return false;
    }

    private FieldBinding GetBinding(int handle, BoundExportGroup boundGroup)
    {
        if ((uint)handle < (uint)boundGroup.FieldsByHandle.Length)
        {
            return boundGroup.FieldsByHandle[handle];
        }

        return default;
    }

    private static DecodedPayloadResult CreateDecodedPayloadResult(
        object payloadObject,
        int decodedFieldCount,
        IReadOnlyList<DecodedReplayField> diagnosticFields,
        ref FieldDecodeContext context)
    {
        if (payloadObject is IDecodedPayloadEventEmitter eventEmitter)
        {
            eventEmitter.EmitDecodedEvents(ref context);
        }

        return new DecodedPayloadResult(payloadObject, decodedFieldCount, diagnosticFields);
    }

    private static ILogger<FieldPayloadParser> GetLogger(FieldDecodeContext context) =>
        context.LoggerFactory?.CreateLogger<FieldPayloadParser>() ?? NullLogger<FieldPayloadParser>.Instance;
}
