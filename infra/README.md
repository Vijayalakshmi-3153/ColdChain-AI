# Infrastructure (ColdChain AI)

Configuration files for the services orchestrated by Docker Compose.

| Service    | Port (host) | Purpose                                   | Config |
|------------|-------------|-------------------------------------------|--------|
| PostgreSQL | 5432        | Relational storage (trips, alerts, users)  | –      |
| Redis      | 6379        | Cache for latest sensor readings           | –      |
| MinIO      | 9000 / 9001 | S3-compatible object storage               | –      |
| Mosquitto  | 1883        | MQTT broker for IoT sensor messages         | `mosquitto/mosquitto.conf` |
| FastAPI    | 8000        | Backend API                                | –      |
| Frontend   | 5173 / 80   | React + Vite app                           | –      |

All services are defined in the root `docker-compose.yml`.