using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.Combat;

public sealed class MulticastNotifyDamagePointParameters : DamageParameters<MulticastNotifyDamagePointParameters>
{
    public override string Path => "/Script/ShooterGame.DamageableComponent:MulticastNotifyDamage_Point";

    public uint DamagedComponent { get; set; }
    public string? DamagedBone { get; set; }
    public bool IsWallPenetration { get; set; }
    public float FalloffMultiplier { get; set; }
    public ValorantRawPayload? DamageDirection { get; set; }
    public ValorantRawPayload? DamageImpactLocation { get; set; }
    public ValorantRawPayload? DamageImpactNormal { get; set; }
    public ValorantRawPayload? DamageImpactBoneRelativeLocation { get; set; }
    public ValorantRawPayload? AssistsList { get; set; }
    public ValorantRawPayload? AssistType { get; set; }
    public uint Assister { get; set; }
    public uint AssistingEquippableClass { get; set; }
    public ValorantRawPayload? AssistTag { get; set; }
    public int KillsForKiller { get; set; }
    public int KillsForVictim { get; set; }
    public uint DeathAnimMontage { get; set; }
    public ValorantRawPayload? DeathMontageEffectOverride { get; set; }
    public ValorantRawPayload? DeathMontageEffectOverrideContext { get; set; }
    public bool DeathMontageEffectOverrideIsQueued { get; set; }

    protected override void Configure()
    {
        AddSharedFields();
        AddPropertyHandle(26, x => x.DamagedComponent, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(27, x => x.DamagedBone, ExportCategory.Gunplay).FName();
        AddPropertyHandle(28, "bIsWallPenetration", x => x.IsWallPenetration, ExportCategory.Gunplay).Bool();
        AddPropertyHandle(29, x => x.FalloffMultiplier, ExportCategory.Gunplay).Float();
        AddRaw(30, x => x.DamageDirection, "DamageDirection");
        AddRaw(31, x => x.DamageImpactLocation, "DamageImpactLocation");
        AddRaw(32, x => x.DamageImpactNormal, "DamageImpactNormal");
        AddRaw(33, x => x.DamageImpactBoneRelativeLocation, "DamageImpactBoneRelativeLocation");
        AddRaw(34, x => x.AssistsList, "AssistsList");
        AddRaw(35, x => x.AssistType, "AssistType");
        AddPropertyHandle(36, x => x.Assister, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(37, x => x.AssistingEquippableClass, ExportCategory.Gunplay).ObjectNetGuid();
        AddRaw(38, x => x.AssistTag, "AssistTag");
        AddPropertyHandle(40, x => x.KillsForKiller, ExportCategory.Gunplay).Int32();
        AddPropertyHandle(41, x => x.KillsForVictim, ExportCategory.Gunplay).Int32();
        AddPropertyHandle(42, x => x.DeathAnimMontage, ExportCategory.Gunplay).ObjectNetGuid();
        AddRaw(43, x => x.DeathMontageEffectOverride, "DeathMontageEffectOverride");
        AddRaw(44, x => x.DeathMontageEffectOverrideContext, "DeathMontageEffectOverrideContext");
        AddPropertyHandle(45, "bDeathMontageEffectOverrideIsQueued", x => x.DeathMontageEffectOverrideIsQueued, ExportCategory.Gunplay).Bool();
    }
}