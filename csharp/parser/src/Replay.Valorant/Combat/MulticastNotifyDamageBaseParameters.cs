using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.Combat;

public sealed class MulticastNotifyDamageBaseParameters : DamageParameters<MulticastNotifyDamageBaseParameters>
{
    public override string Path => "/Script/ShooterGame.DamageableComponent:MulticastNotifyDamage_Base";

    public int KillsForKiller { get; set; }
    public int KillsForVictim { get; set; }
    public uint DeathAnimMontage { get; set; }
    public ValorantRawPayload? DeathMontageEffectOverride { get; set; }
    public ValorantRawPayload? DeathMontageEffectOverrideContext { get; set; }
    public bool DeathMontageEffectOverrideIsQueued { get; set; }

    protected override void Configure()
    {
        AddSharedFields();
        AddDeathFields(32);
    }

    private void AddDeathFields(uint firstHandle)
    {
        AddPropertyHandle(firstHandle, x => x.KillsForKiller, ExportCategory.Gunplay).Int32();
        AddPropertyHandle(firstHandle + 1, x => x.KillsForVictim, ExportCategory.Gunplay).Int32();
        AddPropertyHandle(firstHandle + 2, x => x.DeathAnimMontage, ExportCategory.Gunplay).ObjectNetGuid();
        AddRaw(firstHandle + 3, x => x.DeathMontageEffectOverride, "DeathMontageEffectOverride");
        AddRaw(firstHandle + 4, x => x.DeathMontageEffectOverrideContext, "DeathMontageEffectOverrideContext");
        AddPropertyHandle(firstHandle + 5, "bDeathMontageEffectOverrideIsQueued", x => x.DeathMontageEffectOverrideIsQueued, ExportCategory.Gunplay).Bool();
    }
}