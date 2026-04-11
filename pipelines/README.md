# Lab 05: Vertex AI Pipelines

## What You'll Learn

- Pipeline structure (components, artifacts, flow)
- Kubeflow Pipelines SDK
- Compiling pipelines to JSON
- Running on Vertex AI

---

## Pipeline Architecture

```
┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐
│ Load Data  │───►│  Process   │───►│   Train    │───►│  Evaluate  │
│            │    │   Data     │    │   Model    │    │   Model    │
└────────────┘    └────────────┘    └────────────┘    └────────────┘
     │                  │                  │                  │
     ▼                  ▼                  ▼                  ▼
  Artifact          Artifacts           Artifact          Metrics
  (raw data)     (train/test data)      (model)       (accuracy etc)
```

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Component** | Single step (function with @component decorator) |
| **Artifact** | Data passed between components (files, models) |
| **Metrics** | Numbers logged to UI (accuracy, loss) |
| **Pipeline** | Workflow connecting components |

---

## Files

| File | Purpose |
|------|---------|
| `my_first_pipeline.py` | Pipeline definition |
| `run_pipeline.py` | Submit to Vertex AI |
| `my_first_pipeline.json` | Compiled pipeline (generated) |

---

## Step 1: Compile Pipeline (Local)

```bash
pip install -r requirements.txt
python my_first_pipeline.py
```

This generates `my_first_pipeline.json`

---

## Step 2: Run on Vertex AI

### Option A: Console Upload

1. Go to Pipelines → Upload
2. Select `my_first_pipeline.json`
3. Create Run → Set parameters
4. Submit

### Option B: Python Script

```bash
# First, authenticate
gcloud auth application-default login

# Run
python run_pipeline.py
```

---

## Cost Estimate

| Component | Cost |
|-----------|------|
| This pipeline | ~$1-2 |
| AutoML training | $20-100+ |
| Just compiling | Free |

---

## System Design Concepts

### DAG (Directed Acyclic Graph)
- Pipeline flows one direction
- No circular dependencies
- Enables parallel execution

### Idempotency
- Each component can be rerun independently
- If step 3 fails, restart from step 3 (not step 1)

### Artifacts
- Data persisted in Cloud Storage
- Versioned automatically
- Enables reproducibility

---

## Next Steps

1. View pipeline in Vertex AI Console
2. Modify components
3. Add more steps
4. Connect to real data sources
