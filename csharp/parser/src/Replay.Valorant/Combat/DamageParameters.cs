using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.Combat;

public abstract class DamageParameters<T> : ExportGroupDescriptor<T>
    where T : DamageParameters<T>
{
    public override ExportCategory Categories => ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public float DamageTaken { get; set; }
    public float DamageDealt { get; set; }
    public bool DamageKilledTarget { get; set; }
    public bool AliveAfterDamage { get; set; }
    public uint EventInstigator { get; set; }
    public uint DamageCauser { get; set; }
    public ValorantRawPayload? DamageOrigin { get; set; }
    public ValorantEquippable? EquippableUsed { get; set; }
    public uint DamageType { get; set; }
    public ValorantRawPayload? LifeChangeEvents { get; set; }
    public uint ChangedComponent { get; set; }
    public ValorantRawPayload? LifeResult { get; set; }
    public float DeltaLife { get; set; }
    public bool AliveAfterChange { get; set; }
    public uint EventInstigatorPawn { get; set; }
    public uint DamagerPlayerState { get; set; }
    public uint KillCreditPlayerState { get; set; }
    public EAresRegionalDamage? RegionalDamage { get; set; }
    public uint Character { get; set; }
    public float NetTimestamp { get; set; }
    public int RespawnNumber { get; set; }
    public int LifeChangeEventIndex { get; set; }
    public int VictimRespawnNumber { get; set; }
    public bool EquippableUsedZoomed { get; set; }
    public bool EquippableUsedInFocusMode { get; set; }

    protected void AddSharedFields()
    {
        AddPropertyHandle(0, x => x.DamageTaken, ExportCategory.Gunplay).Float();
        AddPropertyHandle(1, x => x.DamageDealt, ExportCategory.Gunplay).Float();
        AddPropertyHandle(2, "bDamageKilledTarget", x => x.DamageKilledTarget, ExportCategory.Gunplay).Bool();
        AddPropertyHandle(3, "bAliveAfterDamage", x => x.AliveAfterDamage, ExportCategory.Gunplay).Bool();
        AddPropertyHandle(4, x => x.EventInstigator, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(5, x => x.DamageCauser, ExportCategory.Gunplay).ObjectNetGuid();
        AddRaw(6, x => x.DamageOrigin, "DamageOrigin");
        AddPropertyHandle(7, x => x.EquippableUsed, ExportCategory.Gunplay).Decode(ValorantPayloadDecoders.Equippable);
        AddPropertyHandle(8, x => x.DamageType, ExportCategory.Gunplay).ObjectNetGuid();
        AddRaw(9, x => x.LifeChangeEvents, "LifeChangeEvents");
        AddPropertyHandle(10, x => x.ChangedComponent, ExportCategory.Gunplay).ObjectNetGuid();
        AddRaw(11, x => x.LifeResult, "LifeResult");
        AddPropertyHandle(12, x => x.DeltaLife, ExportCategory.Gunplay).Float();
        AddPropertyHandle(13, "bAliveAfterChange", x => x.AliveAfterChange, ExportCategory.Gunplay).Bool();
        AddPropertyHandle(15, x => x.EventInstigatorPawn, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(16, x => x.DamagerPlayerState, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(17, x => x.KillCreditPlayerState, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(18, x => x.RegionalDamage, ExportCategory.Gunplay).EnumByte();
        AddPropertyHandle(19, x => x.Character, ExportCategory.Gunplay).ObjectNetGuid();
        AddPropertyHandle(20, x => x.NetTimestamp, ExportCategory.Gunplay).Float();
        AddPropertyHandle(21, x => x.RespawnNumber, ExportCategory.Gunplay).Int32();
        AddPropertyHandle(22, x => x.LifeChangeEventIndex, ExportCategory.Gunplay).Int32();
        AddPropertyHandle(23, x => x.VictimRespawnNumber, ExportCategory.Gunplay).Int32();
        AddPropertyHandle(24, "bEquippableUsedZoomed", x => x.EquippableUsedZoomed, ExportCategory.Gunplay).Bool();
        AddPropertyHandle(25, "bEquippableUsedInFocusMode", x => x.EquippableUsedInFocusMode, ExportCategory.Gunplay).Bool();
    }

    protected void AddRaw(uint handle, System.Linq.Expressions.Expression<Func<T, ValorantRawPayload?>> property, string typeName) =>
        AddPropertyHandle(handle, property, ExportCategory.Gunplay).Decode(ValorantPayloadDecoders.RawPayload(typeName));
}
