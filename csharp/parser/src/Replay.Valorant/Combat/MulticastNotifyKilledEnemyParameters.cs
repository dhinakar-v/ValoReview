using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Combat;

public sealed class MulticastNotifyKilledEnemyParameters
    : ExportGroupDescriptor<MulticastNotifyKilledEnemyParameters>
{
    public override string Path => "/Script/ShooterGame.ShooterCharacter:MulticastNotifyKilledEnemy";
    public override ExportCategory Categories => ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public uint KillerCharacter { get; set; }
    public uint KilledCharacter { get; set; }
    public int MultikillLevel { get; set; }

    protected override void Configure()
    {
        AddPropertyHandle(0, x => x.KillerCharacter, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(1, x => x.KilledCharacter, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(2, x => x.MultikillLevel, ExportCategory.Gunplay).Int32();
    }
}