using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;
using Replay.Valorant.Combat;

namespace Replay.Valorant.Descriptors.Effects.Replay;

public sealed class ReplayPlayContinuousEffectAtLocationParameters
    : ExportGroupDescriptor<ReplayPlayContinuousEffectAtLocationParameters>, IDecodedPayloadEventEmitter
{
    private const string AttackVectorPrefix = "FiringState.AttackVector.";

    public override string Path => "/Script/ShooterGame.ReplayEffectComponent:ReplayPlayContinuousEffectAtLocation";
    public override ExportCategory Categories => ExportCategory.Effects | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.ClassNetCache;
    public override FieldStreamGrammar Grammar => FieldStreamGrammar.FunctionParameters;

    public ulong? EffectId { get; set; }
    public string? SourceId { get; set; }
    public bool? IsLocalEffect { get; set; }
    public bool? IsTransient { get; set; }
    public uint? WaitOnReplicationActor { get; set; }
    public EffectDataFloat[]? FloatValues { get; set; }
    public EffectDataVector[]? VectorValues { get; set; }
    public EffectDataObject[]? ObjectValues { get; set; }
    public FVector? Location { get; set; }
    public FRotator? Rotation { get; set; }
    public EAresAlliance? AllianceFilter { get; set; }
    public float? StartMovementTime { get; set; }

    protected override void Configure()
    {
        AddPropertyHandle(1, "EffectID", x => x.EffectId, ExportCategory.Effects).UInt64();
        AddPropertyHandle(2, "SourceID", x => x.SourceId, ExportCategory.Effects).FName();
        AddPropertyHandle(3, "bLocalEffect", x => x.IsLocalEffect, ExportCategory.Effects).Bool();
        AddPropertyHandle(4, "bTransient", x => x.IsTransient, ExportCategory.Effects).Bool();
        AddPropertyHandle(5, x => x.WaitOnReplicationActor, ExportCategory.Effects).ObjectNetGuid();
        AddPropertyHandle(6, x => x.FloatValues, ExportCategory.Gunplay).RepLayoutDynamicArray<EffectDataFloat>();
        AddPropertyHandle(10, x => x.VectorValues, ExportCategory.Gunplay).RepLayoutDynamicArray<EffectDataVector>();
        AddPropertyHandle(14, x => x.ObjectValues, ExportCategory.Gunplay).RepLayoutDynamicArray<EffectDataObject>();
        AddPropertyHandle(26, x => x.Location, ExportCategory.Effects | ExportCategory.Gunplay).FVector();
        AddPropertyHandle(27, x => x.Rotation, ExportCategory.Effects | ExportCategory.Gunplay).FRotatorShort();
        AddPropertyHandle(28, x => x.AllianceFilter, ExportCategory.Effects).EnumRemainingBits();
        AddPropertyHandle(29, x => x.StartMovementTime, ExportCategory.Effects | ExportCategory.Gunplay).Float();
    }

    public void EmitDecodedEvents(ref FieldDecodeContext context)
    {
        context.EventSink?.Emit(new ValorantShotReceived(
            context.CurrentTimeSeconds,
            context.CurrentPacketId,
            context.ActorNetGuid.Value,
            context.ObjectNetGuid.Value,
            context.ChannelIndex,
            CreateShot()));
    }

    public ValorantShot CreateShot()
    {
        return new ValorantShot(
            EffectId,
            StartMovementTime,
            SourceId,
            IsLocalEffect,
            IsTransient,
            WaitOnReplicationActor,
            AllianceFilter,
            Location,
            Rotation,
            GetFloat("FiringState.AmmoRemaining"),
            GetFloat("FiringState.NumProjectiles"),
            GetFloat("FiringState.RandomSeed"),
            GetFloat("FiringState.TracerOption"),
            GetFloat("FiringState.BurstShotNumber"),
            GetFloat("FiringState.YawSwitch"),
            GetObject("FiringState.FiringPlayerState"),
            GetObject("FiringState.FiringState"),
            GetAttackVectors(),
            GetObject("FXC.Equippable"),
            Equippable: null);
    }

    private float? GetFloat(string tagName)
    {
        return FloatValues?.FirstOrDefault(value => value.Name?.TagName == tagName)?.Float;
    }

    private uint? GetObject(string tagName)
    {
        return ObjectValues?.FirstOrDefault(value => value.Name?.TagName == tagName)?.Object;
    }

    private IReadOnlyList<FVector> GetAttackVectors()
    {
        if (VectorValues is null)
        {
            return [];
        }

        return VectorValues
            .Select(value => new
            {
                Index = GetAttackVectorIndex(value.Name?.TagName),
                value.Vector,
            })
            .Where(value => value.Index is >= 1 and <= 15 && value.Vector.HasValue)
            .OrderBy(value => value.Index)
            .Select(value => value.Vector!.Value)
            .ToArray();
    }

    private static int? GetAttackVectorIndex(string? tagName)
    {
        if (tagName is null || !tagName.StartsWith(AttackVectorPrefix, StringComparison.Ordinal))
        {
            return null;
        }

        return int.TryParse(tagName[AttackVectorPrefix.Length..], out var index) ? index : null;
    }
}
