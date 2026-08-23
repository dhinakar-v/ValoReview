using Replay.Models.Descriptors;

namespace Replay.Valorant.Descriptors.Agents.Pandemic.SmokeScreen;

public class SmokeScreenManagerClassNetCacheDescriptor : ClassNetCacheDescriptor<SmokeScreenManagerClassNetCacheDescriptor>
{
    public override string Path => "/Game/Characters/Pandemic/S0/Ability_E/GameObject_Pandemic_E_SmokeScreenManager.GameObject_Pandemic_E_SmokeScreenManager_C_ClassNetCache";
    
    protected override void Configure()
    {
        AddFunction<MulticastAddSmokeScreenPointParameters>(
            "MulticastAddSmokeScreenPoint",
            "/Game/Characters/Pandemic/S0/Ability_E/GameObject_Pandemic_E_SmokeScreenManager.GameObject_Pandemic_E_SmokeScreenManager_C:MulticastAddSmokeScreenPoint",
            ExportCategory.Ability);
    }
}