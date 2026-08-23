using Replay.Models.Descriptors;

namespace Replay.Unreal.Parsing;

public sealed class BoundClassNetCache
{
    public required string Path { get; init; }
    public required ClassNetCacheDescriptor SourceDescriptor { get; init; }
    public FieldStreamGrammar Grammar { get; init; }
    public bool Enabled { get; init; }
    public required BoundRpcFunction[] FunctionsByHandle { get; init; }
}