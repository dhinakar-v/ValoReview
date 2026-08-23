using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class AbilityRechargeCooldownComponentDescriptor
    : ExportGroupDescriptor<AbilityRechargeCooldownComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.AbilityRechargeCooldownComponent";
    public override ExportCategory Categories => ExportCategory.Ability;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public float CooldownSeconds { get; set; }
    public float TempChargeCooldownSeconds { get; set; }
    public float CooldownFinishTimestamp { get; set; }
    public float TempChargeCooldownFinishTimestamp { get; set; }
    public int ChargesInUse { get; set; }
    public bool CooldownPaused { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.CooldownSeconds).Float();
        AddProperty(x => x.TempChargeCooldownSeconds).Float();
        AddProperty(x => x.CooldownFinishTimestamp).Float();
        AddProperty(x => x.TempChargeCooldownFinishTimestamp).Float();
        AddProperty(x => x.ChargesInUse).Int32();
        AddProperty("bCooldownPaused", x => x.CooldownPaused).Bool();
    }
}