# Cloud Deployment Path

CricketPulse runs locally on Docker for the demo, but the architecture was
designed for easy cloud migration. Nothing in the business logic needs to
change — only the infrastructure adapters.

## AWS reference architecture

```
                +--------------------+
                |   IPL data source  |    (real API in prod;
                |   or simulator     |     simulator for demo)
                +----------+---------+
                           |
                           v
                +--------------------+       +-----------------+
                |    AWS MSK         |------>|  AWS Lambda /   |
                |  (managed Kafka)   |       |  ECS Fargate    |----+
                +--------------------+       |  (consumer)     |    |
                                             +--------+--------+    |
                                                      |             |
                                                      v             v
                                             +------------------+  +---------------+
                                             | Snowflake (or    |  | SageMaker     |
                                             | Redshift)        |  | endpoint      |
                                             | bronze/silver/   |  | (win-prob     |
                                             | gold schemas     |  | inference)    |
                                             +---------+--------+  +-------+-------+
                                                       |                   |
                                                       v                   v
                                             +--------------------+  +----------------+
                                             | AWS MWAA           |  | AWS Bedrock    |
                                             | (Managed Airflow)  |  | (Gemini/Claude)|
                                             +---------+----------+  +-------+--------+
                                                       |                     |
                                                       v                     v
                                                    +------------------------------+
                                                    | ECS Fargate: Streamlit       |
                                                    | behind ALB + Cognito         |
                                                    +------------------------------+
```

## Line-by-line swaps

| Local component               | Cloud equivalent                                   | Files to change                                            |
| ----------------------------- | -------------------------------------------------- | ---------------------------------------------------------- |
| Kafka (Docker)                | AWS MSK (SASL/IAM) or Confluent Cloud              | `.env` -> `KAFKA_BOOTSTRAP_SERVERS`                        |
| DuckDB file                   | Snowflake / BigQuery / Redshift                    | `src/warehouse/db.py` (swap `duckdb.connect` for `snowflake.connector.connect`) |
| Airflow (Docker LocalExecutor)| MWAA (AWS) or Cloud Composer (GCP)                 | Upload `airflow/dags/` to S3 bucket, MWAA picks up         |
| Streamlit (local port 8501)   | ECS Fargate service behind ALB + Route 53          | Add `Dockerfile.dashboard` + `task-definition.json`        |
| Gemini API                    | AWS Bedrock (Anthropic Claude) / GCP Vertex AI     | `src/genai/llm.py` (swap `ChatGoogleGenerativeAI`)         |
| Local `.env` secrets          | AWS Secrets Manager                                | `src/common/config.py` (add secrets loader)                |

## Cost estimate (AWS, low-traffic)

| Service           | Monthly cost |
| ----------------- | ------------ |
| MSK (t3.small)    | ~$70         |
| MWAA (small)      | ~$300        |
| Snowflake (X-Small warehouse, 4 hrs/day) | ~$100 |
| ECS Fargate (dashboard, 0.5 vCPU) | ~$15 |
| Bedrock (per-token) | ~$5 (low usage) |
| **Total**         | **~$490/mo** |

For a portfolio project, keep everything on the **free tiers** by using
Confluent Cloud (free), Snowflake trial ($400 credits), and running Airflow
locally.

## Migration steps

1. **Provision MSK cluster + create topics** (same names as local).
2. **Bootstrap Snowflake schemas** by running `src/warehouse/schema.sql`
   via the Snowflake SQL editor.
3. **Package the consumer as a Docker image**, push to ECR, deploy as an
   ECS Fargate service.
4. **Upload the DAGs to the MWAA bucket**; MWAA auto-scans.
5. **Build the dashboard image** (`streamlit run` as CMD), push, deploy to ECS.
6. **Point Secrets Manager -> env vars** via ECS task definition.

Done. Same code, different infrastructure.
