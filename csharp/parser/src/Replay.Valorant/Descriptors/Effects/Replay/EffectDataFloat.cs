using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Effects.Replay;

public sealed class EffectDataFloat : ExportGroupDescriptor<EffectDataFloat>
{
    public FGameplayTag? Name { get; set; }
    public float? Float { get; set; }

    protected override void Configure()
    {
        AddPropertyHandle(7, "58", x => x.Name, ExportCategory.Gunplay).FGameplayTag();
        AddPropertyHandle(8, x => x.Float, ExportCategory.Gunplay).Float();
    }
}
