from google.cloud import bigquery

SCHEMAS = {
    "matches": [
        bigquery.SchemaField("match_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP"),
        bigquery.SchemaField("raw", "STRING"),
    ],
    "top_players": [
        bigquery.SchemaField("snapshot_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("rank_position", "INT64"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP"),
        bigquery.SchemaField("raw", "STRING"),
    ],
}