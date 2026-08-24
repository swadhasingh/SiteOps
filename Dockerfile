# Not needed yet — this matters once you reach the Working Guide's
# "Local Testing Checklist" and GCP sections. Kept here now so the repo
# skeleton matches the Build Plan doc from day one.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY data/ data/
# After `npm run build` in frontend/ (Working Guide Step 9):
# COPY frontend/dist/ src/static/
EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
