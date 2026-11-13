# Custom Airflow image: same base as Defense 1, but the extra Python packages are baked in
# at build time (Defense 1 pip-installed them at every container start via
# _PIP_ADDITIONAL_REQUIREMENTS: slow, and racy between the 4 Airflow containers).
FROM apache/airflow:3.1.0-python3.12

ARG AIRFLOW_VERSION=3.1.0
ARG PYTHON_VERSION=3.12

COPY requirements.txt /tmp/requirements.txt
# Installed under Airflow's official constraints file -> nothing in the base image is upgraded
# and an incompatible pin fails the *build* instead of breaking at runtime.
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
