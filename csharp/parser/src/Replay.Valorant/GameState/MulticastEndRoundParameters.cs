using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class MulticastEndRoundParameters : ExportGroupDescriptor<MulticastEndRoundParameters>
{
    public override string Path => "/Script/ShooterGame.ShooterGameState:MulticastEndRound";
    public override ExportCategory Categories => ExportCategory.GameState;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public int NewRoundNumber { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.NewRoundNumber, ExportCategory.GameState).Int32();
    }
}