using Replay.Models.Descriptors;
using Replay.Valorant.Movement;

namespace Replay.Valorant.Descriptors;

public sealed class
    BaseReplayControllerClassNetCacheDescriptor : ClassNetCacheDescriptor<BaseReplayControllerClassNetCacheDescriptor>
{
    public override string Path => "/Game/Characters/_Core/BaseReplayController.BaseReplayController_C_ClassNetCache";

    protected override void Configure()
    {
        AddFunction(
                "ReplaysClientReceiveRemoteCharacterUpdatesSingleArrayNoAutonomous",
                "/Script/ShooterGame.ReplayPlayerController:ReplaysClientReceiveRemoteCharacterUpdatesSingleArrayNoAutonomous",
                ExportCategory.Movement)
            .Decode(RemoteCharacterUpdatesRpcDecoder.Instance);

        AddFunction<ClientGamePhaseBeginParameters>(
            "ClientGamePhaseBegin",
            "/Script/ShooterGame.AresPlayerController:ClientGamePhaseBegin",
            ExportCategory.GameState);

        AddFunction<ClientGamePhaseEndedParameters>(
            "ClientGamePhaseEnded",
            "/Script/ShooterGame.AresPlayerController:ClientGamePhaseEnded",
            ExportCategory.GameState);
    }
}