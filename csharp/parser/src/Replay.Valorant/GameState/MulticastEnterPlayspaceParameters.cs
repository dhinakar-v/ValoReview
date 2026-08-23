using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.GameState;

public sealed class MulticastEnterPlayspaceParameters : ExportGroupDescriptor<MulticastEnterPlayspaceParameters>
{
    public override string Path => "/Script/ShooterGame.ShooterGameState:MulticastEnterPlayspace";
    public override ExportCategory Categories => ExportCategory.GameState;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public ValorantRawPayload? PlayspaceComponent { get; set; } // TODO: Implement this object-reference encoding.
    public ValorantRawPayload? NewPlayspace { get; set; } // TODO: Implement this object-reference encoding.
    public bool LeaveCurrentPlayspaces { get; set; }
    public bool ExecuteOnOwner { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.PlayspaceComponent, ExportCategory.GameState)
            .Decode(ValorantPayloadDecoders.RawPayload("PlayspaceComponent"));
        AddProperty(x => x.NewPlayspace, ExportCategory.GameState)
            .Decode(ValorantPayloadDecoders.RawPayload("NewPlayspace"));
        AddProperty("bLeaveCurrentPlayspaces", x => x.LeaveCurrentPlayspaces, ExportCategory.GameState).Bool();
        AddProperty("bExecuteOnOwner", x => x.ExecuteOnOwner, ExportCategory.GameState).Bool();
    }
}