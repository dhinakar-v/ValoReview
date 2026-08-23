namespace Replay.Models.Descriptors;

public sealed class RpcDescriptor
{
    public required string Name { get; init; }
    public required string FunctionExportPath { get; init; }
    public uint? Handle { get; init; }
    public ExportCategory Categories { get; init; }
    public ExportGroupDescriptor? ParameterDescriptor { get; init; }
    public IReadOnlyList<FieldDescriptor> Fields { get; init; } = [];
    public IRpcDecoderDescriptor? Decoder { get; init; }
}