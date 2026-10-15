SILVER_MATCHES = """
CREATE OR REPLACE TABLE `{silver}.matches`
PARTITION BY DATE(game_creation) AS
SELECT
  match_id,
  TIMESTAMP_MILLIS(CAST(JSON_VALUE(raw, '$.info.gameCreation') AS INT64)) AS game_creation,
  CAST(JSON_VALUE(raw, '$.info.gameDuration') AS INT64) AS game_duration_s,
  CAST(JSON_VALUE(raw, '$.info.queueId') AS INT64) AS queue_id,
  JSON_VALUE(raw, '$.info.gameMode') AS game_mode,
  JSON_VALUE(raw, '$.info.gameVersion') AS game_version,
  REGEXP_EXTRACT(JSON_VALUE(raw, '$.info.gameVersion'), r'^(\\d+\\.\\d+)') AS patch,
  ingested_at
FROM `{bronze}.matches`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (PARTITION BY match_id ORDER BY ingested_at DESC) = 1
"""

SILVER_TOP_PLAYERS = """
CREATE OR REPLACE TABLE `{silver}.top_players` AS
SELECT
  snapshot_date,
  rank_position,
  JSON_VALUE(raw, '$.puuid') AS puuid,
  CAST(JSON_VALUE(raw, '$.leaguePoints') AS INT64) AS league_points,
  CAST(JSON_VALUE(raw, '$.wins') AS INT64) AS wins,
  CAST(JSON_VALUE(raw, '$.losses') AS INT64) AS losses
FROM `{bronze}.top_players`
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY snapshot_date, rank_position ORDER BY ingested_at DESC
) = 1
"""

SILVER_PARTICIPANTS = """
CREATE OR REPLACE TABLE `{silver}.participants`
PARTITION BY DATE(game_creation)
CLUSTER BY champion_name, puuid AS
WITH dedup AS (
  SELECT match_id, raw
  FROM `{bronze}.matches`
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY match_id ORDER BY ingested_at DESC) = 1
)
SELECT
  d.match_id,
  m.game_creation,
  m.game_duration_s,
  m.queue_id,
  m.patch,
  JSON_VALUE(p, '$.puuid') AS puuid,
  CONCAT(JSON_VALUE(p, '$.riotIdGameName'), '#', JSON_VALUE(p, '$.riotIdTagline')) AS riot_id,
  JSON_VALUE(p, '$.championName') AS champion_name,
  CAST(JSON_VALUE(p, '$.teamId') AS INT64) AS team_id,
  NULLIF(JSON_VALUE(p, '$.teamPosition'), '') AS position,
  CAST(JSON_VALUE(p, '$.kills') AS INT64) AS kills,
  CAST(JSON_VALUE(p, '$.deaths') AS INT64) AS deaths,
  CAST(JSON_VALUE(p, '$.assists') AS INT64) AS assists,
  CAST(JSON_VALUE(p, '$.win') AS BOOL) AS win,
  CAST(JSON_VALUE(p, '$.goldEarned') AS INT64) AS gold_earned,
  CAST(JSON_VALUE(p, '$.totalMinionsKilled') AS INT64)
    + CAST(JSON_VALUE(p, '$.neutralMinionsKilled') AS INT64) AS cs,
  CAST(JSON_VALUE(p, '$.totalDamageDealtToChampions') AS INT64) AS damage_to_champions,
  CAST(JSON_VALUE(p, '$.visionScore') AS INT64) AS vision_score,
  CAST(JSON_VALUE(p, '$.timePlayed') AS INT64) AS time_played_s,
  CAST(JSON_VALUE(p, '$.gameEndedInSurrender') AS BOOL) AS ended_in_surrender
FROM dedup d
JOIN `{silver}.matches` m USING (match_id),
UNNEST(JSON_QUERY_ARRAY(d.raw, '$.info.participants')) AS p
"""

GOLD_CHAMPION_STATS = """
CREATE OR REPLACE TABLE `{gold}.champion_stats` AS
WITH base AS (
  SELECT * FROM `{silver}.participants`
  WHERE queue_id = 420 AND game_duration_s >= 300 AND position IS NOT NULL
),
patch_totals AS (
  SELECT patch, COUNT(DISTINCT match_id) AS matches
  FROM base
  GROUP BY patch
)
SELECT
  patch,
  champion_name,
  position,
  COUNT(*) AS games,
  COUNTIF(win) AS wins,
  SAFE_DIVIDE(COUNTIF(win), COUNT(*)) AS win_rate,
  SAFE_DIVIDE(COUNT(*), ANY_VALUE(t.matches)) AS pick_rate,
  SAFE_DIVIDE(SUM(kills + assists), SUM(deaths)) AS kda,
  AVG(SAFE_DIVIDE(cs, game_duration_s / 60)) AS cs_per_min,
  AVG(damage_to_champions) AS avg_damage,
  AVG(vision_score) AS avg_vision
FROM base
JOIN patch_totals t USING (patch)
GROUP BY patch, champion_name, position
"""

GOLD_TOP_PLAYER_STATS = """
CREATE OR REPLACE TABLE `{gold}.top_player_stats` AS
WITH latest AS (
  SELECT * FROM `{silver}.top_players`
  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `{silver}.top_players`)
),
games AS (
  SELECT
    puuid,
    ANY_VALUE(riot_id) AS riot_id,
    COUNT(*) AS games,
    COUNTIF(win) AS wins,
    SAFE_DIVIDE(SUM(kills + assists), SUM(deaths)) AS kda,
    AVG(SAFE_DIVIDE(cs, game_duration_s / 60)) AS cs_per_min,
    APPROX_TOP_COUNT(champion_name, 1)[OFFSET(0)].value AS most_played_champion
  FROM `{silver}.participants`
  WHERE queue_id = 420 AND game_duration_s >= 300
  GROUP BY puuid
)
SELECT
  l.snapshot_date,
  l.rank_position,
  l.puuid,
  g.riot_id,
  l.league_points,
  g.games,
  SAFE_DIVIDE(g.wins, g.games) AS win_rate,
  g.kda,
  g.cs_per_min,
  g.most_played_champion
FROM latest l
LEFT JOIN games g USING (puuid)
ORDER BY l.rank_position
"""

TRANSFORMS = {
    "silver_matches": SILVER_MATCHES,
    "silver_top_players": SILVER_TOP_PLAYERS,
    "silver_participants": SILVER_PARTICIPANTS,
    "gold_champion_stats": GOLD_CHAMPION_STATS,
    "gold_top_player_stats": GOLD_TOP_PLAYER_STATS,
}