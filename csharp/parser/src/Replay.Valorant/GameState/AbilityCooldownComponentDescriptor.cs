using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class AbilityCooldownComponentDescriptor
    : ExportGroupDescriptor<AbilityCooldownComponentDescriptor>
{
    public override string Path =>
        "/Game/Characters/Components/Comp_Ability_CooldownComponent.Comp_Ability_CooldownComponent_C";
    public override ExportCategory Categories => ExportCategory.Ability;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public float CooldownSeconds { get; set; }
    public float StartTimeStamp { get; set; }
    public bool CooldownActive { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.CooldownSeconds).Float();
        AddProperty(x => x.StartTimeStamp).Float();
        AddProperty(x => x.CooldownActive).Bool();
    }
}