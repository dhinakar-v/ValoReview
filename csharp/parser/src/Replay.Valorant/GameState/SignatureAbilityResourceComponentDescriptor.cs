using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class SignatureAbilityResourceComponentDescriptor
    : ResourceComponentDescriptor<SignatureAbilityResourceComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.SignatureAbilityResourceComponent";

    public int ChargesBoughtThisRound { get; set; }
    public int CurrentTemporaryCharges { get; set; }
    public int TotalChargesAllowedToPurchaseThisRound { get; set; }
    public int AuthSignatureChargeAmount { get; set; }

    protected override void Configure()
    {
        base.Configure();
        AddProperty(x => x.ChargesBoughtThisRound).Int32();
        AddProperty(x => x.CurrentTemporaryCharges).Int32();
        AddProperty(x => x.TotalChargesAllowedToPurchaseThisRound).Int32();
        AddProperty(x => x.AuthSignatureChargeAmount).Int32();
    }
}