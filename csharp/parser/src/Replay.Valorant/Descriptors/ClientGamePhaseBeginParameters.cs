using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors;

public sealed class ClientGamePhaseBeginParameters : ExportGroupDescriptor<ClientGamePhaseBeginParameters>
{
    public override string Path => "/Script/ShooterGame.AresPlayerController:ClientGamePhaseBegin";
    public override ExportCategory Categories => ExportCategory.GameState;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public byte NewPhase { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.NewPhase, ExportCategory.GameState).EnumByte();
    }
}