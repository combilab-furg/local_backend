
---

````markdown
# 📦 Local Backend

A backend service built with **Python**, **FastAPI**, and **Uvicorn**.  
This guide explains how to install, configure, and run the backend locally.

---

## 🚀 1. Requirements

Make sure you have:

- Python **3.10+**
- pip
- virtualenv (optional but recommended)
- Git

---

## 📥 2. Clone the Repository

```bash
git clone https://github.com/combilab-furg/local_backend.git
cd local_backend
````

---

## 🧪 3. Create & Activate Virtual Environment

### Create venv:

```bash
python3 -m venv venv
```

### Activate venv:

#### Linux / macOS:

```bash
source venv/bin/activate
```

#### Windows:

```bash
venv\Scripts\activate
```

---

## 📦 4. Install Dependencies

```bash
pip install -r requirements.txt
```

---

---

## ▶️ 5. Run the Backend

Start the server with Uvicorn:

```bash
cd local_backend
source venv/bin/activate
python3 main.py
```


---


