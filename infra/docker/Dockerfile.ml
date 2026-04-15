FROM public.ecr.aws/lambda/python:3.12

# Install ML dependencies
RUN pip install --no-cache-dir joblib scikit-learn==1.7.2 pandas

# Copy model files
COPY MLRepo/models/logistic_regression/selected/runs/2026-04-15_115456/ ${LAMBDA_TASK_ROOT}/model/
COPY MLRepo/src/training/preprocess.py ${LAMBDA_TASK_ROOT}/src/training/preprocess.py
COPY MLRepo/src/training/__init__.py ${LAMBDA_TASK_ROOT}/src/training/__init__.py
COPY MLRepo/src/__init__.py ${LAMBDA_TASK_ROOT}/src/__init__.py

# Copy handler
COPY infra/lambda/ml_handler.py ${LAMBDA_TASK_ROOT}/

CMD ["ml_handler.handler"]
