from pydantic import BaseModel, ConfigDict


class RiotModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Account(RiotModel):
    puuid: str
    gameName: str
    tagLine: str


class LeagueEntry(RiotModel):
    puuid: str | None = None
    summonerId: str | None = None
    leaguePoints: int
    wins: int = 0
    losses: int = 0


class Participant(RiotModel):
    puuid: str
    riotIdGameName: str | None = None
    riotIdTagline: str | None = None
    championName: str
    teamId: int
    teamPosition: str = ""
    kills: int
    deaths: int
    assists: int
    win: bool
    goldEarned: int = 0
    totalMinionsKilled: int = 0
    neutralMinionsKilled: int = 0
    totalDamageDealtToChampions: int = 0
    visionScore: int = 0
    timePlayed: int = 0
    gameEndedInSurrender: bool = False
    gameEndedInEarlySurrender: bool = False


class MatchMetadata(RiotModel):
    matchId: str
    participants: list[str]


class MatchInfo(RiotModel):
    gameId: int
    gameCreation: int
    gameDuration: int
    gameMode: str
    queueId: int
    gameVersion: str
    participants: list[Participant]


class Match(RiotModel):
    metadata: MatchMetadata
    info: MatchInfo


class PlayerMatches(BaseModel):
    riot_id: str
    puuid: str
    match_ids: list[str]
    matches: list[Match]
    saved_to: str | None = None