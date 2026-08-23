using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors;

public sealed class ClientGamePhaseEndedParameters : ExportGroupDescriptor<ClientGamePhaseEndedParameters>
{
    public override string Path => "/Script/ShooterGame.AresPlayerController:ClientGamePhaseEnded";
    public override ExportCategory Categories => ExportCategory.GameState;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public byte OldPhase { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.OldPhase, ExportCategory.GameState).EnumByte();
    }
}