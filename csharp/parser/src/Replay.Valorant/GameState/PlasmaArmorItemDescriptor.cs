using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class PlasmaArmorItemDescriptor
    : ArmorItemDescriptor<PlasmaArmorItemDescriptor>
{
    public override string Path => "/Game/Gear/PlasmaArmor/PlasmaArmorItem.PlasmaArmorItem_C";

    public bool RegenActive { get; set; }
    public double MaxRegenPool { get; set; }
    public double CurrentRegenPool { get; set; }

    protected override void Configure()
    {
        base.Configure();
        AddProperty(x => x.RegenActive).Bool();
        AddProperty(x => x.MaxRegenPool).Double();
        AddProperty(x => x.CurrentRegenPool).Double();
    }
}