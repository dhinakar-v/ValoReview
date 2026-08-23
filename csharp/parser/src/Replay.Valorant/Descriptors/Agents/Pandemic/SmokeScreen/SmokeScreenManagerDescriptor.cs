using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Agents.Pandemic.SmokeScreen;

public class SmokeScreenManagerDescriptor : ExportGroupDescriptor<SmokeScreenManagerDescriptor>
{
    public override string Path => "/Game/Characters/Pandemic/S0/Ability_E/GameObject_Pandemic_E_SmokeScreenManager.GameObject_Pandemic_E_SmokeScreenManager_C";
    public override ExportCategory Categories => ExportCategory.Ability;
    
    public uint Owner { get; set; }
    public uint Instigator { get; set; }
    public double CurrentFuelLevel { get; set; }
    public bool WallActivated { get; set; }
    
    protected override void Configure()
    {
        AddProperty(x => x.Owner).ObjectNetGuid();
        AddProperty(x => x.CurrentFuelLevel).Double();
        AddProperty(x => x.WallActivated).Bool();
        AddProperty(x => x.Instigator).ObjectNetGuid();
    }
}