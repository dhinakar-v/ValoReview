namespace Replay.Valorant.GameState;

public enum EAresGamePhase
{
    NotStarted = 0,
    GameStarted = 1,
    BetweenRounds = 2,
    RoundStarting = 3,
    InRound = 4,
    RoundEnding = 5,
    SwitchingTeams = 6,
    GameEnded = 7,
    Count = 8,
    Invalid = 254,
    EAresGamePhase_MAX = 255,
}
