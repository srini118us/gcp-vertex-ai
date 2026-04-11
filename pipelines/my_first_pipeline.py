"""
Lab 05: Vertex AI Pipeline (Clean Version)
No emojis to avoid encoding issues
"""

from kfp import dsl
from kfp.dsl import component, Output, Input, Artifact, Metrics
from kfp import compiler


@component(
    base_image="python:3.11-slim",
    packages_to_install=["pandas"]
)
def load_data(
    num_samples: int,
    output_data: Output[Artifact]
) -> None:
    import pandas as pd
    
    data = {
        "id": list(range(1, num_samples + 1)),
        "feature_1": [i * 1.5 for i in range(1, num_samples + 1)],
        "feature_2": [i * 2.0 for i in range(1, num_samples + 1)],
        "target": [i % 2 for i in range(1, num_samples + 1)]
    }
    
    df = pd.DataFrame(data)
    output_path = output_data.path + ".csv"
    df.to_csv(output_path, index=False)
    
    output_data.metadata["output_path"] = output_path
    output_data.metadata["num_rows"] = len(df)
    
    print("Loaded {} samples".format(len(df)))


@component(
    base_image="python:3.11-slim",
    packages_to_install=["pandas", "scikit-learn"]
)
def process_data(
    input_data: Input[Artifact],
    train_data: Output[Artifact],
    test_data: Output[Artifact],
    test_size: float = 0.2
) -> None:
    import pandas as pd
    from sklearn.model_selection import train_test_split
    
    input_path = input_data.path + ".csv"
    df = pd.read_csv(input_path)
    
    df["feature_1_normalized"] = df["feature_1"] / df["feature_1"].max()
    df["feature_2_normalized"] = df["feature_2"] / df["feature_2"].max()
    
    train_df, test_df = train_test_split(df, test_size=test_size, random_state=42)
    
    train_path = train_data.path + ".csv"
    test_path = test_data.path + ".csv"
    
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)
    
    train_data.metadata["num_rows"] = len(train_df)
    test_data.metadata["num_rows"] = len(test_df)
    
    print("Split data: {} train, {} test".format(len(train_df), len(test_df)))


@component(
    base_image="python:3.11-slim",
    packages_to_install=["pandas", "scikit-learn", "joblib"]
)
def train_model(
    train_data: Input[Artifact],
    model_artifact: Output[Artifact]
) -> None:
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    import joblib
    
    train_path = train_data.path + ".csv"
    df = pd.read_csv(train_path)
    
    X = df[["feature_1_normalized", "feature_2_normalized"]]
    y = df["target"]
    
    model = LogisticRegression(max_iter=100)
    model.fit(X, y)
    
    model_path = model_artifact.path + ".pkl"
    joblib.dump(model, model_path)
    
    model_artifact.metadata["model_type"] = "LogisticRegression"
    
    print("Model trained and saved")


@component(
    base_image="python:3.11-slim",
    packages_to_install=["pandas", "scikit-learn", "joblib"]
)
def evaluate_model(
    model_artifact: Input[Artifact],
    test_data: Input[Artifact],
    metrics: Output[Metrics]
) -> None:
    import pandas as pd
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    import joblib
    
    model_path = model_artifact.path + ".pkl"
    test_path = test_data.path + ".csv"
    
    model = joblib.load(model_path)
    df = pd.read_csv(test_path)
    
    X_test = df[["feature_1_normalized", "feature_2_normalized"]]
    y_test = df["target"]
    
    y_pred = model.predict(X_test)
    
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    
    metrics.log_metric("accuracy", accuracy)
    metrics.log_metric("precision", precision)
    metrics.log_metric("recall", recall)
    
    print("Accuracy: {:.4f}".format(accuracy))
    print("Precision: {:.4f}".format(precision))
    print("Recall: {:.4f}".format(recall))


@dsl.pipeline(
    name="my-first-ml-pipeline-v3",
    description="Simple ML pipeline"
)
def my_first_pipeline(
    num_samples: int = 100,
    test_size: float = 0.2
):
    load_task = load_data(num_samples=num_samples)
    
    process_task = process_data(
        input_data=load_task.outputs["output_data"],
        test_size=test_size
    )
    
    train_task = train_model(
        train_data=process_task.outputs["train_data"]
    )
    
    evaluate_task = evaluate_model(
        model_artifact=train_task.outputs["model_artifact"],
        test_data=process_task.outputs["test_data"]
    )


if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=my_first_pipeline,
        package_path="my_first_pipeline_v3.json"
    )
    
    print("=" * 60)
    print("Pipeline V3 compiled successfully!")
    print("Output: my_first_pipeline_v3.json")
    print("=" * 60)
