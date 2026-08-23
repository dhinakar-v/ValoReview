using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.GameState;

public sealed class MulticastReceivePlayerTemporaryDeathEventBaseParameters
    : ExportGroupDescriptor<MulticastReceivePlayerTemporaryDeathEventBaseParameters>
{
    public override string Path =>
        "/Script/ShooterGame.ShooterGameState:MulticastReceivePlayerTemporaryDeathEvent_Base";

    public override ExportCategory Categories => ExportCategory.GameState | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public uint DamagerPlayer { get; set; }
    public uint DownedPlayer { get; set; }
    public ValorantRawPayload? DamageResponseData { get; set; } // TODO: Implement this type.
    public uint EquippableUsed { get; set; }
    public bool RecoversInstantly { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.DamagerPlayer, ExportCategory.Gunplay).ObjectNetGuid();
        AddProperty(x => x.DownedPlayer, ExportCategory.Gunplay).ObjectNetGuid();
        AddProperty(x => x.DamageResponseData, ExportCategory.Gunplay)
            .Decode(ValorantPayloadDecoders.RawPayload("FNetworkedDamageResponseData"));
        AddProperty(x => x.EquippableUsed, ExportCategory.Inventory | ExportCategory.Gunplay)
            .ObjectNetGuid();
        AddProperty("bRecoversInstantly", x => x.RecoversInstantly, ExportCategory.GameState).Bool();
    }
}