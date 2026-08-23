using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class AbilityRechargeComponentDescriptor
    : ExportGroupDescriptor<AbilityRechargeComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.AbilityRechargeComponent";
    public override ExportCategory Categories => ExportCategory.Ability;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public int MaxCharges { get; set; }
    public int CurrentCharges { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.MaxCharges).Int32();
        AddProperty(x => x.CurrentCharges).Int32();
    }
}