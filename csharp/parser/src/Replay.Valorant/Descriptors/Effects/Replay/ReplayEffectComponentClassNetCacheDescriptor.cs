using Replay.Models.Descriptors;

namespace Replay.Valorant.Descriptors.Effects.Replay;

public sealed class ReplayEffectComponentClassNetCacheDescriptor
    : ClassNetCacheDescriptor<ReplayEffectComponentClassNetCacheDescriptor>
{
    public override string Path => "/Script/ShooterGame.ReplayEffectComponent_ClassNetCache";

    protected override void Configure()
    {
        AddFunctionHandle<ReplayPlayContinuousEffectAtLocationParameters>(
                0,
                "ReplayPlayContinuousEffectAtLocation",
                "/Script/ShooterGame.ReplayEffectComponent:ReplayPlayContinuousEffectAtLocation",
                ExportCategory.Effects | ExportCategory.Gunplay);
        AddFunctionHandle(
            1,
            "ReplayPlayOneShotEffectAtLocation",
            "/Script/ShooterGame.ReplayEffectComponent:ReplayPlayOneShotEffectAtLocation",
            ExportCategory.Effects);
        AddFunctionHandle(
            2,
            "ReplayStopContinuousEffectAtLocation",
            "/Script/ShooterGame.ReplayEffectComponent:ReplayStopContinuousEffectAtLocation",
            ExportCategory.Effects);
    }
}
