# Cloud-Native Identity & Observability: OAuth2 + Prometheus

<div align="center">
  
  ![Python](https://img.shields.io/badge/Backend-Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
  ![OAuth2](https://img.shields.io/badge/Security-OAuth2_Provider-blue?style=for-the-badge)
  ![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-E6522C?style=for-the-badge&logo=prometheus&logoColor=white)
  ![Grafana](https://img.shields.io/badge/Visualization-Grafana-F46800?style=for-the-badge&logo=grafana&logoColor=white)
  ![Locust](https://img.shields.io/badge/Load_Testing-Locust-4EAA25?style=for-the-badge)

</div>

> **ABOUT THIS PROJECT:**
> This repository demonstrates a complete **DevSecOps** and **Site Reliability Engineering (SRE)** loop. It bridges the gap between Application Security (building a custom OAuth2 Authorization Server) and Cloud-Native Observability (Prometheus & Grafana).
> 
> Furthermore, it integrates **Locust** for Chaos Engineering and Load Testing, simulating massive concurrent traffic to validate API resilience and generate real-time metrics under stress.

<div align="center">
  <img width="800" src="assets/dashboard.png" alt="OAuth2 Backend Metrics Dashboard" />
</div>

---

## Architecture & Key Features

* **Identity & Access Management (OAuth2):** Custom modular backend (`oauth2_routes.py`, `admin_routes.py`) acting as a secure identity provider with encrypted token generation and SQLite persistence via ORM (`models.py`).
* **Cloud-Native Telemetry (`metrics.py`):** The application exposes a custom `/metrics` endpoint, instrumented to feed **Prometheus** (Pull-based telemetry) with data regarding HTTP response codes, latency, and active connections.
* **Load Testing & Chaos Engineering (`locustfile.py`):** Automated traffic simulation using **Locust** to bombard the authentication endpoints, ensuring the system can handle concurrent authorization flows without degradation.
* **Modern Dependency Management:** Utilizes `pyproject.toml` and `uv` for lightning-fast, reproducible dependency resolution.

---

## Project Structure

```text
Cloud-Native-OAuth2-Observability
 ┣ 📂 assets/          # Grafana dashboard previews
 ┣ 📂 docs/            # Technical reports and presentation slides
 ┃ ┣ 📜 presentation_slides.pdf
 ┃ ┗ 📜 technical_report.pdf
 ┣ 📂 load-testing/    # Locust stress-testing scripts
 ┃ ┗ 📜 locustfile.py
 ┣ 📂 prometheus/      # Telemetry scrapers configuration
 ┃ ┗ 📜 prometheus.yml
 ┣ 📂 src/             # Core Backend Application
 ┃ ┣ 📜 app.py
 ┃ ┣ 📜 oauth2_routes.py
 ┃ ┣ 📜 admin_routes.py
 ┃ ┣ 📜 metrics.py
 ┃ ┣ 📜 models.py
 ┃ ┣ 📜 database.py
 ┃ ┗ 📜 seed.py
 ┣ 📜 pyproject.toml   # Project metadata and dependencies
 ┗ 📜 uv.lock          # Dependency lockfile
```

---

## Getting Started & Reproduction Guide

### Prerequisites
* Python 3
* `uv` (Fast Python package installer) or standard `pip`
* Prometheus & Grafana

### 1. Environment & Database Setup
Clone the repository, install dependencies, and seed the local database:

```bash
git clone [https://github.com/imoroc/Cloud-Native-OAuth2-Observability.git](https://github.com/imoroc/Cloud-Native-OAuth2-Observability.git)
cd Cloud-Native-OAuth2-Observability

# Install dependencies using uv (or pip)
uv sync

# Navigate to source and initialize the mock database
cd src
python3 seed.py
```

### 2. Run the Backend Service
Start the authorization server:
```bash
python3 app.py
```
*The application will start, and the telemetry endpoint will be exposed at `http://localhost:[YOUR_PORT]/metrics`.*

### 3. Prometheus Configuration
Start Prometheus pointing to the provided configuration file to begin scraping the backend:
```bash
prometheus --config.file=../prometheus/prometheus.yml
```

### 4. Load Testing (Generating Traffic)
To see the metrics spike in real-time on your Grafana instance, launch the Locust swarm against the backend:
```bash
cd ../load-testing/
locust -f locustfile.py
```
*Open `http://localhost:8089` to configure the number of concurrent users and spawn rate.*

---

### 👨‍💻 Authors

Iván Moro Cienfuegos, Pablo March Ortega and Nicolás Reyes Gutiérrez
