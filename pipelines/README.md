# Pipelines - Vertex AI ML Pipelines

Build and run ML pipelines on Vertex AI using Kubeflow Pipelines SDK.

## What You'll Learn

- Pipeline structure (components, artifacts, flow)
- Kubeflow Pipelines SDK basics
- Compiling pipelines to JSON
- Running pipelines on Vertex AI

## Architecture

```
+------------+    +------------+    +------------+    +------------+
| Load Data  |--->|  Process   |--->|   Train    |--->|  Evaluate  |
|            |    |   Data     |    |   Model    |    |   Model    |
+------------+    +------------+    +------------+    +------------+
      |                |                  |                 |
      v                v                  v                 v
  Artifact        Artifacts           Artifact          Metrics
 (raw data)    (train/test)          (model)        (accuracy)
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Component** | Single step (function with @component decorator) |
| **Artifact** | Data passed between components (files, models) |
| **Metrics** | Numbers logged to UI (accuracy, loss) |
| **Pipeline** | Workflow connecting components |

## Files

| File | Purpose |
|------|---------|
| `my_first_pipeline.py` | Pipeline definition |
| `run_pipeline.py` | Submit to Vertex AI |
| `my_first_pipeline.json` | Compiled pipeline (generated) |
| `requirements.txt` | Python dependencies |

## Setup

```bash
cd pipelines
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt

gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

## Step 1: Compile Pipeline

```bash
python my_first_pipeline.py
```

This generates `my_first_pipeline.json`

## Step 2: Run on Vertex AI

### Option A: Console Upload

1. Go to Vertex AI > Pipelines > Upload
2. Select `my_first_pipeline.json`
3. Create Run > Set parameters
4. Submit

### Option B: Python Script

```bash
python run_pipeline.py
```

## Cost Estimate

| Component | Cost |
|-----------|------|
| This pipeline | ~$1-2 |
| AutoML training | $20-100+ |
| Just compiling | Free |

## Key Concepts

### DAG (Directed Acyclic Graph)
- Pipeline flows one direction
- No circular dependencies
- Enables parallel execution

### Idempotency
- Each component can be rerun independently
- If step 3 fails, restart from step 3

### Artifacts
- Data persisted in Cloud Storage
- Versioned automatically
- Enables reproducibility

## Next Steps

1. View pipeline in Vertex AI Console
2. Modify components
3. Add more steps
4. Connect to real data sources
