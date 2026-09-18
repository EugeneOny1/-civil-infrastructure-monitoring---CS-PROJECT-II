# Computer Vision-Based Civil Infrastructure Monitoring System
### Automated Structural Defect Detection and Assessment
**Author:** Eugene Onyango Odhiambo (166333, ISC 4B)  
**Supervisor:** Dr. Deperias Kerre  
**Institution:** School of Computing and Engineering Sciences, Strathmore University  

---

## 🏗️ Overview

This project implements an end-to-end civil infrastructure defect monitoring system combining **Computer Vision (SSD-MobileNetV2)**, **Agile Scrum software engineering**, and the **CRISP-DM** data science framework. The platform provides:

1. **Citizen Defect Reporting & AI Pre-Assessment (FR-02, FR-03, FR-04)**: Image submission via mobile web, automated defect classification across three target classes (**Cracks**, **Potholes**, **Surface Deterioration**), bounding-box localization, and image-derived relative severity calculation (Low, Medium, Critical).
2. **Citizen Defect Tracking (FR-08)**: Transparent lifecycle monitoring of submitted tickets.
3. **Engineer Monitoring Dashboard (FR-07, FR-09)**: Active defect queue, SLA turnaround metrics, structural degradation trends over 6 months, and severity prioritization.
4. **Professional Review Terminal (FR-06)**: Human-in-the-loop engineering validation allowing licensed engineers to confirm or override AI defect classifications and record certification notes.
5. **System Governance (FR-10)**: Administrator portal for professional account verification.

---

## 📁 Repository Structure

```
civil-infrastructure-monitoring/
│
├── backend/
│   ├── app/
│   │   ├── models/           # OOAD Domain Classes (User, Asset, Report, Assessment, Review)
│   │   ├── routes/           # Modular REST API Blueprints (Auth, Reports, Assets, Reviews, Analytics, Admin)
│   │   ├── services/         # Core Services (MongoDB, Severity Assessment, SSD-MobileNetV2 Model)
│   │   ├── utils/            # Role-Based Access Control & File Upload Helpers
│   │   ├── config.py         # Application Configuration
│   │   └── __init__.py       # Flask App Factory & CORS
│   │
│   ├── uploads/              # Local image storage for submitted inspection photos
│   ├── run.py                # Backend launch script
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # Environment variables template
│
├── frontend/
│   ├── index.html            # Responsive SPA matching Figures 4.6, 4.7, 4.8 wireframes
│   ├── css/
│   │   ├── main.css          # Curated dark slate engineering theme & glassmorphism
│   │   └── components.css    # Detection frame, canvas styling, telemetry, and KPI cards
│   └── js/
│       ├── api.js            # REST API client
│       ├── submission.js     # Defect capture, GPS tag & canvas bounding box renderer
│       ├── dashboard.js      # KPI metrics, degradation trend canvas chart, queue filter
│       ├── review.js         # Professional sign-off & defect inspection terminal
│       └── app.js            # View routing, role switching, and notifications
│
├── notebooks/                # CRISP-DM Machine Learning Pipeline (Google Colab)
│   ├── 01_Data_Preparation_and_Environment.ipynb
│   ├── 02_Data_Inspection.ipynb
│   ├── 03_Annotation_Validation.ipynb
│   ├── 04_TFRecord_Generation.ipynb
│   ├── 05_Model_Training.ipynb
│   ├── 06_Model_Evaluation.ipynb
│   └── 07_Inference_Demo.ipynb
│
├── configs/                  # TensorFlow Object Detection pipeline configuration & label_map.pbtxt
├── docs/                     # Proposal PDF, OOAD Class Diagram & Database Schema
├── models/                   # Exported SSD-MobileNetV2 SavedModel or TFLite weights
├── .vscode/
│   └── settings.json         # Configures Antigravity to automatically use .venv
├── .gitignore                # Excludes .venv/, uploads/, heavy model weights, and caches
└── README.md
```

---

## 🚀 Quick Start Guide

### 1. Virtual Environment Activation
The project's isolated environment `.venv` is configured in `.vscode/settings.json`. To activate in your terminal:

**Windows PowerShell:**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows Command Prompt:**
```cmd
.venv\Scripts\activate.bat
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` inside `backend/`:
```bash
copy backend\.env.example backend\.env
```
*(Optional: Provide your MongoDB Atlas connection string in `backend/.env` under `MONGO_URI`. If left default, the backend automatically uses its robust built-in development store.)*

### 3. Launch the Application Server
Run the Flask server:
```bash
.venv\Scripts\python.exe backend/run.py
```
Or with activated virtual environment:
```bash
python backend/run.py
```

Open your browser and navigate to:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🧠 Machine Learning Model Integration

- **Model Architecture**: Single Shot MultiBox Detector (SSD) with MobileNetV2 backbone.
- **Target Defect Classes**: `Crack`, `Pothole`, `Surface Deterioration`.
- **Inference Service**: Located at `backend/app/services/ai_service.py`.
  - While training is executing on **Google Colab**, the web application runs in high-fidelity computer vision simulation mode, computing realistic bounding boxes, defect classes, and relative severity.
  - When training completes, export your weights (`ssd_mobilenet_v2.tflite` or `saved_model/`) into `models/`. The backend automatically loads the trained weights for live inference!