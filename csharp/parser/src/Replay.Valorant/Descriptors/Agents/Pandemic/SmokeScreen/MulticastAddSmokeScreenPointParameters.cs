using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Agents.Pandemic.SmokeScreen;

public sealed class MulticastAddSmokeScreenPointParameters : ExportGroupDescriptor<MulticastAddSmokeScreenPointParameters>
{
    public override string Path => "/Game/Characters/Pandemic/S0/Ability_E/GameObject_Pandemic_E_SmokeScreenManager.GameObject_Pandemic_E_SmokeScreenManager_C:MulticastAddSmokeScreenPoint";
    public override ExportCategory Categories => ExportCategory.Ability;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public FVector Translation { get; set; }
    public FVector Scale3D { get; set; }
    public FVector ProjectileLocation { get; set; }
    public float ValveDistance { get; set; }
    public uint CreatingProjectile { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.Translation, ExportCategory.Ability).FVector();
        AddProperty(x => x.Scale3D, ExportCategory.Ability).FVector();
        AddProperty(x => x.ProjectileLocation, ExportCategory.Ability).FVector();
        AddProperty(x => x.ValveDistance, ExportCategory.Ability).Double();
        AddProperty(x => x.CreatingProjectile, ExportCategory.Ability).ObjectNetGuid();
    }
}