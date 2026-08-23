using Replay.Models.Descriptors;
using Replay.Valorant.Combat;

namespace Replay.Valorant.Descriptors.Agents;

internal static class AgentClassNetCacheDescriptors
{
    private const string KillFunctionName = "MulticastNotifyKilledEnemy";
    private const string KillFunctionPath = "/Script/ShooterGame.ShooterCharacter:MulticastNotifyKilledEnemy";

    public static IReadOnlyList<ClassNetCacheDescriptor> Create(IEnumerable<ExportGroupDescriptor> agentDescriptors)
    {
        return agentDescriptors
            .Select(agent => new ClassNetCacheDescriptor(
                agent.Path + "_ClassNetCache",
                [CreateKillRpc()]))
            .ToArray();
    }

    private static RpcDescriptor CreateKillRpc()
    {
        var parameters = new MulticastNotifyKilledEnemyParameters();
        return new RpcDescriptor
        {
            Name = KillFunctionName,
            FunctionExportPath = KillFunctionPath,
            Categories = ExportCategory.Gunplay,
            ParameterDescriptor = parameters,
            Fields = parameters.Fields,
        };
    }
}
