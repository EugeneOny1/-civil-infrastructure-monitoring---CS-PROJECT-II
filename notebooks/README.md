# Machine Learning Pipeline Notebooks (CRISP-DM Framework)

This directory houses the Jupyter / Google Colab experimental notebooks following the **Cross-Industry Standard Process for Data Mining (CRISP-DM)** methodology described in Chapter 3 of the project proposal:

| Notebook | Phase | Objective |
| :--- | :--- | :--- |
| `01_Data_Preparation_and_Environment.ipynb` | Data Preparation | Colab GPU setup, TensorFlow Object Detection API installation, and dataset download. |
| `02_Data_Inspection.ipynb` | Data Understanding | Exploratory data analysis (EDA) across SDNET2018, RDD2020, and Kenyan field photos. |
| `03_Annotation_Validation.ipynb` | Data Preparation | Pascal VOC / COCO annotation verification for the 3 target classes (`Crack`, `Pothole`, `Surface Deterioration`). |
| `04_TFRecord_Generation.ipynb` | Data Preparation | Serialization into `train.record` and `val.record` (70:15:15 split). |
| `05_Model_Training.ipynb` | Modeling | Fine-tuning the SSD-MobileNetV2 architecture with transfer learning checkpoints. |
| `06_Model_Evaluation.ipynb` | Evaluation | Computing precision, recall, F1-score, and mean Average Precision (mAP >= 80%). |
| `07_Inference_Demo.ipynb` | Deployment Prep | Exporting SavedModel and TFLite weights to `../models/` for the Flask web application. |
