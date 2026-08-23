using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class EquipmentChargeComponentDescriptor
    : ResourceComponentDescriptor<EquipmentChargeComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.EquipmentChargeComponent";

    public int MaxCharges { get; set; }
    public int ChargesBoughtThisRound { get; set; }
    public int CurrentTemporaryCharges { get; set; }
    public int TotalChargesAllowedToPurchaseThisRound { get; set; }

    protected override void Configure()
    {
        base.Configure();
        AddProperty(x => x.MaxCharges).Int32();
        AddProperty(x => x.ChargesBoughtThisRound).Int32();
        AddProperty(x => x.CurrentTemporaryCharges).Int32();
        AddProperty(x => x.TotalChargesAllowedToPurchaseThisRound).Int32();
    }
}