using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Agents.Mage;

public class CoveAbilityDescriptor : ExportGroupDescriptor<CoveAbilityDescriptor>
{
    public override string Path => "/Game/Characters/Mage/S0/Ability_E/GameObject_Mage_E_WorldSmoke.GameObject_Mage_E_WorldSmoke_C";
    public override ExportCategory Categories => ExportCategory.Ability;

    public uint? Instigator { get; set; }
    public uint? Owner { get; set; }
    public FRepMovement? ReplicatedMovement { get; set; }
    
    protected override void Configure()
    {
        AddProperty(x => x.Owner).ObjectNetGuid();
        AddProperty(x => x.Instigator).ObjectNetGuid();
        AddProperty(x => x.ReplicatedMovement).ReplicatedMovement();
    }
}