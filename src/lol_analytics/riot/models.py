from pydantic import BaseModel, ConfigDict


class RiotModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Account(RiotModel):
    puuid: str
    gameName: str
    tagLine: str


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