using Replay.Models.Descriptors;

namespace Replay.Valorant.Combat;

public sealed class DamageableComponentClassNetCacheDescriptor
    : ClassNetCacheDescriptor<DamageableComponentClassNetCacheDescriptor>
{
    public override string Path => "/Script/ShooterGame.DamageableComponent_ClassNetCache";
    protected override void Configure()
    {
        AddFunctionHandle<MulticastNotifyDamageBaseParameters>(
            0, "MulticastNotifyDamage_Base",
            "/Script/ShooterGame.DamageableComponent:MulticastNotifyDamage_Base",
            ExportCategory.Gunplay);
        AddFunctionHandle<MulticastNotifyDamagePointParameters>(
            1, "MulticastNotifyDamage_Point",
            "/Script/ShooterGame.DamageableComponent:MulticastNotifyDamage_Point",
            ExportCategory.Gunplay);
    }
}