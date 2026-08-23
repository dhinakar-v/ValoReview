using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.GameState;

public sealed class MulticastResetForRespawnParameters : ExportGroupDescriptor<MulticastResetForRespawnParameters>
{
    public override string Path => "/Script/ShooterGame.AresGameStateBase:MulticastResetForRespawn";
    public override ExportCategory Categories => ExportCategory.GameState;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public ValorantRawPayload? ShooterCharacter { get; set; } // TODO: Implement this object-reference encoding.
    public FTransform? SpawnTransform { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.ShooterCharacter, ExportCategory.GameState)
            .Decode(ValorantPayloadDecoders.RawPayload("ShooterCharacter"));
        AddProperty(x => x.SpawnTransform, ExportCategory.GameState).Transform();
    }
}