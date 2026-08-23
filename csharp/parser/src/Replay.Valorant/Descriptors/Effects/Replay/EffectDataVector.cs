using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Effects.Replay;

public sealed class EffectDataVector : ExportGroupDescriptor<EffectDataVector>
{
    public FGameplayTag? Name { get; set; }
    public FVector? Vector { get; set; }

    protected override void Configure()
    {
        AddPropertyHandle(11, "58", x => x.Name, ExportCategory.Gunplay).FGameplayTag();
        AddPropertyHandle(12, "59", x => x.Vector, ExportCategory.Gunplay).FVector();
    }
}
