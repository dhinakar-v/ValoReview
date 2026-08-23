using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Agents.Wraith;

public class DarkCoverAbilityDescriptor : ExportGroupDescriptor<DarkCoverAbilityDescriptor>
{
    public override string Path => "/Game/Characters/Wraith/S0/Ability_4/Zone_Wraith_4_Smoke.Zone_Wraith_4_Smoke_C";
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