using Replay.Encoding.Net;
using Replay.Models.Events;
using Replay.Models.Net;
using Replay.Valorant.GameState;

namespace Replay.Valorant.Combat;

internal sealed class ValorantShotEventEnricher : IReplayEventSink
{
    private const int MaxOuterDepth = 16;

    private readonly IReplayEventSink _inner;
    private readonly NetGuidCache _netGuidCache;
    private readonly Dictionary<uint, uint> _characterByPlayerState = [];
    private readonly Dictionary<uint, uint> _selectedEquippableByCharacter = [];
    private readonly Dictionary<uint, ValorantEquippable> _equippableByActor = [];

    public ValorantShotEventEnricher(IReplayEventSink inner, NetGuidCache netGuidCache)
    {
        _inner = inner;
        _netGuidCache = netGuidCache;
    }

    public void Emit(ReplayEvent replayEvent)
    {
        switch (replayEvent)
        {
            case ActorSpawned spawned:
                TrackActor(spawned);
                break;
            case ExportGroupReceived exportGroup:
                TrackExportGroup(exportGroup);
                break;
            case RpcReceived rpc:
                TrackWeaponRpc(rpc);
                break;
            case ValorantShotReceived shot:
                var fireMode = ValorantShotFireModeResolver.Resolve(shot.Shot, _netGuidCache);
                replayEvent = shot with
                {
                    Shot = shot.Shot with
                    {
                        Equippable = ResolveShotEquippable(shot.Shot),
                        FireMode = fireMode.FireMode,
                        FireModeEvidence = fireMode.Evidence,
                    },
                };
                break;
        }

        _inner.Emit(replayEvent);
    }

    private void TrackActor(ActorSpawned spawned)
    {
        if (ValorantEquippableResolver.TryResolve(
                spawned.ActorNetGuid,
                [spawned.ReplicationClassPath, spawned.ArchetypePath, spawned.ActorPath],
                out var equippable))
        {
            _equippableByActor[spawned.ActorNetGuid] = equippable;
        }
    }

    private void TrackExportGroup(ExportGroupReceived exportGroup)
    {
        switch (exportGroup.Payload)
        {
            case BombPlayerStateDescriptor playerState:
                TrackPlayerState(exportGroup.ActorNetGuid, playerState);
                break;
            case AresInventoryDescriptor inventory:
                TrackInventory(exportGroup.ActorNetGuid, inventory);
                break;
        }
    }

    private void TrackPlayerState(uint playerStateNetGuid, BombPlayerStateDescriptor playerState)
    {
        if (playerState.HasDecoded(nameof(BombPlayerStateDescriptor.PossessedCharacter)))
        {
            SetCharacter(playerStateNetGuid, playerState.PossessedCharacter);
            return;
        }

        if (playerState.HasDecoded(nameof(BombPlayerStateDescriptor.SpawnedCharacter)))
        {
            SetCharacter(playerStateNetGuid, playerState.SpawnedCharacter);
        }
    }

    private void TrackInventory(uint actorNetGuid, AresInventoryDescriptor inventory)
    {
        var characterNetGuid = inventory.HasDecoded(nameof(AresInventoryDescriptor.Character)) &&
                              inventory.Character != 0
            ? inventory.Character
            : actorNetGuid;
        if (characterNetGuid == 0)
        {
            return;
        }

        if (inventory.HasDecoded(nameof(AresInventoryDescriptor.CurrentEquippable)))
        {
            SetSelectedEquippable(characterNetGuid, inventory.CurrentEquippable);
            return;
        }

        if (inventory.HasDecoded(nameof(AresInventoryDescriptor.NewCurrentEquippable)))
        {
            SetSelectedEquippable(characterNetGuid, inventory.NewCurrentEquippable);
        }
    }

    private void TrackWeaponRpc(RpcReceived rpc)
    {
        if (ValorantEquippableResolver.TryResolveClassNetCachePath(rpc.ClassPath, rpc.ActorNetGuid, out var equippable))
        {
            _equippableByActor[rpc.ActorNetGuid] = equippable;
        }
    }

    private ValorantEquippable? ResolveShotEquippable(ValorantShot shot)
    {
        var fromEffect = ResolveEquippable(shot.EffectEquippable);
        if (fromEffect is not null)
        {
            return fromEffect;
        }

        var fromFiringState = ResolveFromFiringState(shot.FiringState);
        if (fromFiringState is not null)
        {
            return fromFiringState;
        }

        if (shot.FiringPlayerState is not { } playerStateNetGuid ||
            !_characterByPlayerState.TryGetValue(playerStateNetGuid, out var characterNetGuid) ||
            !_selectedEquippableByCharacter.TryGetValue(characterNetGuid, out var equippableNetGuid))
        {
            return null;
        }

        return ResolveEquippable(equippableNetGuid);
    }

    private ValorantEquippable? ResolveEquippable(uint? equippableNetGuid)
    {
        if (equippableNetGuid is not { } value || value == 0)
        {
            return null;
        }

        if (_equippableByActor.TryGetValue(value, out var equippable))
        {
            return equippable;
        }

        var resolved = ValorantEquippableResolver.Resolve(value, _netGuidCache);
        return resolved.Category is not ValorantEquippableCategory.Unknown ? resolved : null;
    }

    private ValorantEquippable? ResolveFromFiringState(uint? firingStateNetGuid)
    {
        if (firingStateNetGuid is not { } value || value == 0)
        {
            return null;
        }

        var current = new NetworkGuid(value);
        for (var depth = 0; depth < MaxOuterDepth && current.IsValid; depth++)
        {
            if (_equippableByActor.TryGetValue(current.Value, out var equippable))
            {
                return equippable;
            }

            if (!_netGuidCache.TryGetOuterNetGuid(current.Value, out current))
            {
                break;
            }
        }

        var resolved = ValorantEquippableResolver.Resolve(value, _netGuidCache);
        return resolved.Category is not ValorantEquippableCategory.Unknown ? resolved : null;
    }

    private void SetCharacter(uint playerStateNetGuid, uint characterNetGuid)
    {
        if (characterNetGuid == 0)
        {
            _characterByPlayerState.Remove(playerStateNetGuid);
            return;
        }

        _characterByPlayerState[playerStateNetGuid] = characterNetGuid;
    }

    private void SetSelectedEquippable(uint characterNetGuid, uint equippableNetGuid)
    {
        if (equippableNetGuid == 0)
        {
            _selectedEquippableByCharacter.Remove(characterNetGuid);
            return;
        }

        _selectedEquippableByCharacter[characterNetGuid] = equippableNetGuid;
    }
}

internal static class ValorantShotFireModeResolver
{
    private const int MaxOuterDepth = 16;
    private static readonly string[] AlternateMarkers =
    [
        "altfire",
        "zoomedfire",
        "zoomedfiring",
        "firingstateburst",
        "burstfiringstate",
        "burstmode",
    ];

    public static ValorantShotFireModeResolution Resolve(ValorantShot shot, NetGuidCache netGuidCache)
    {
        ArgumentNullException.ThrowIfNull(netGuidCache);

        if (ContainsAlternateMarker(shot.SourceId))
        {
            return new ValorantShotFireModeResolution(
                ValorantShotFireMode.Alternate,
                $"source:{shot.SourceId}");
        }

        if (shot.FiringState is not { } firingState || firingState == 0)
        {
            return ValorantShotFireModeResolution.Unknown;
        }

        var paths = new List<string>();
        var current = firingState;
        for (var depth = 0; depth < MaxOuterDepth && current != 0; depth++)
        {
            if (netGuidCache.TryGetPath(current, out var path) && !string.IsNullOrWhiteSpace(path))
            {
                paths.Add(path);
            }

            if (!netGuidCache.TryGetOuterNetGuid(current, out var outer))
            {
                break;
            }

            current = outer.Value;
        }

        if (paths.Count == 0)
        {
            return ValorantShotFireModeResolution.Unknown;
        }

        var evidence = $"firing-state:{string.Join(" -> ", paths)}";
        return paths.Any(ContainsAlternateMarker)
            ? new ValorantShotFireModeResolution(ValorantShotFireMode.Alternate, evidence)
            : new ValorantShotFireModeResolution(ValorantShotFireMode.Primary, evidence);
    }

    private static bool ContainsAlternateMarker(string? value) =>
        !string.IsNullOrWhiteSpace(value) && AlternateMarkers.Any(marker =>
            value.Contains(marker, StringComparison.OrdinalIgnoreCase));
}

internal sealed record ValorantShotFireModeResolution(ValorantShotFireMode FireMode, string? Evidence)
{
    public static ValorantShotFireModeResolution Unknown { get; } =
        new(ValorantShotFireMode.Unknown, null);
}
