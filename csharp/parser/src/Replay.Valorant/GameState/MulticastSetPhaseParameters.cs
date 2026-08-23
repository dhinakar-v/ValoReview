using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class MulticastSetPhaseParameters : ExportGroupDescriptor<MulticastSetPhaseParameters>
{
    public override string Path => "/Script/ShooterGame.ShooterGameState:MulticastSetPhase";
    public override ExportCategory Categories => ExportCategory.GameState;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public byte NewPhase { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.NewPhase, ExportCategory.GameState).EnumByte();
    }
}