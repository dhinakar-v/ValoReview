using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class MulticastReceivePlayerResurrectEventParameters
    : ExportGroupDescriptor<MulticastReceivePlayerResurrectEventParameters>
{
    public override string Path => "/Script/ShooterGame.ShooterGameState:MulticastReceivePlayerResurrectEvent";
    public override ExportCategory Categories => ExportCategory.GameState | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public uint ResurrectorPlayer { get; set; }
    public uint ResurrectedPlayer { get; set; }
    public int KillNumberInRoundForResurrector { get; set; }
    public int KillNumberInRoundForResurrected { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.ResurrectorPlayer, ExportCategory.GameState).ObjectNetGuid();
        AddProperty(x => x.ResurrectedPlayer, ExportCategory.GameState).ObjectNetGuid();
        AddProperty(x => x.KillNumberInRoundForResurrector, ExportCategory.Gunplay).Int32();
        AddProperty(x => x.KillNumberInRoundForResurrected, ExportCategory.Gunplay).Int32();
    }
}